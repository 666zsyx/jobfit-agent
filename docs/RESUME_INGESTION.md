# STEP 13 简历文件接入

## 1. 目标

让 JobFit Agent 支持真实简历文件：

```text
PDF
DOCX
TXT
```

用户不再需要手工准备完整 `raw_text`。

---

## 2. 支持范围

```text
文本型 PDF     支持
DOCX           支持
TXT            支持
扫描版 PDF     不支持，需要 OCR
旧版 .doc      不支持，需要转换为 DOCX
图片简历       不支持
```

不支持时返回明确错误，不做静默降级。

---

## 3. API

### 上传

```http
POST /api/resumes/upload
Content-Type: multipart/form-data
```

字段：

```text
file
resume_id 可选，传入时追加新版本
title 可选
extract_sections 可选，默认 true
```

返回：

```json
{
  "resume_id": 1,
  "resume_version_id": 2,
  "version_no": 1,
  "title": "我的简历",
  "source_type": "pdf",
  "char_count": 3500,
  "preview": "教育经历...",
  "extraction_status": "completed",
  "extraction_error_code": null
}
```

### 列表

```http
GET /api/resumes
```

### 详情

```http
GET /api/resumes/{resume_id}
```

### 重试结构提取

```http
POST /api/resumes/{resume_id}/versions/{resume_version_id}/extract
```

---

## 4. 解析策略

### PDF

```text
pdfplumber 主解析
pypdf 回退
加密 PDF 拒绝
扫描 PDF 返回 scanned_pdf_requires_ocr
```

### DOCX

```text
python-docx
解析段落和表格
校验 ZIP 结构和解压后大小
```

### TXT

```text
UTF-8
GB18030 回退
拒绝二进制内容
```

### 执行

```text
asyncio.to_thread
不阻塞 FastAPI 事件循环
```

---

## 5. 安全限制

```text
文件最大 10 MB
PDF 最大 30 页
简历文本最大 50,000 字符
DOCX 解压后最大 60 MB
扩展名、Content-Type 和文件魔数校验
ZIP Bomb 防护
路径穿越防护
不长期保存原始文件
```

---

## 6. 简历版本

```text
未传 resume_id
→ 创建 Resume + version 1

传入 resume_id
→ 校验简历属于当前用户
→ 追加下一个 ResumeVersion

source_type
→ text / pdf / docx / txt
```

PostgreSQL 约束已扩展到：

```text
text
pdf
docx
txt
```

---

## 7. 结构化提取

流程：

```text
文件
→ raw_text
→ extract_resume_sections
→ extracted_sections
```

状态：

```text
completed
failed
skipped
```

失败策略：

```text
raw_text 仍然保存
resume_version 仍然创建
返回 extraction_status=failed
返回安全错误码
后续可以调用重试接口
```

---

## 8. 与 RAG 的衔接

上传阶段：

```text
文件
→ raw_text
→ ResumeVersion
→ 可选 extracted_sections
```

任务执行阶段：

```text
ResumeVersion
→ Chunking
→ FastEmbed
→ Chroma
→ BM25 / 向量召回
→ RRF
→ Rerank
→ EvidencePack
```

上传接口不同步构建所有向量索引，避免请求过慢。

---

## 9. 错误码

```text
unsupported_file_type
file_too_large
empty_file
corrupted_pdf
encrypted_pdf
scanned_pdf_requires_ocr
invalid_docx
docx_zip_bomb
empty_resume_text
resume_text_too_long
pdf_too_many_pages
invalid_text_encoding
resume_not_found
```

---

## 10. 验证

解析测试：

```text
tests/test_resume_file_parser.py
```

持久化测试：

```text
tests/test_resume_ingestion.py
```

API 测试：

```text
tests/test_resume_upload_api.py
```

真实 PostgreSQL 验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_step13_resume_ingestion.py
```

验证结果：

```text
DOCX / PDF / TXT 解析通过
同一简历追加三个版本通过
source_type 顺序为 docx / pdf / txt
用户数据清理通过
完整测试通过
```

---

## 11. 当前限制

```text
扫描 PDF 和图片需要 OCR
旧版 .doc 需要先转换为 DOCX
没有前端上传页面，当前使用 Swagger
没有对象存储，原始文件不保留
复杂多栏 PDF 抽取质量需要继续评估
```
