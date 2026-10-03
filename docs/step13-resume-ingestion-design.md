# STEP 13 简历文件接入设计

> 状态：设计冻结稿
>
> 创建日期：2026-10-03
>
> 分支：feature/step-13-resume-ingestion
>
> 基线：main@cd60eda

---

## 1. 目标

让 JobFit Agent 支持真实简历文件接入：

```text
PDF
DOCX
TXT
```

完成：

```text
文件上传
格式校验
文本解析
简历版本保存
可选结构化分段
RAG 链路衔接
错误处理
安全限制
测试和文档
```

让用户不再手工提供完整的 `raw_text`。

---

## 2. 非目标

本阶段不处理：

```text
扫描版 PDF OCR
图片简历 OCR
旧版 .doc 二进制格式
复杂简历排版还原
完整简历编辑页面
完整 React 简历管理后台
复杂搜索和分页
```

明确不支持的格式必须返回安全、清晰的错误，而不是静默乱解析。

---

## 3. 支持矩阵

```text
PDF 文本型   支持
DOCX         支持
TXT          支持
扫描 PDF     不支持，返回需要 OCR
旧版 .doc    不支持，提示需要转换为 DOCX
图片         不支持
```

---

## 4. 文件安全限制

默认限制：

```text
单文件最大 10 MB
PDF 最大 30 页
解析文本最大 50,000 字符
DOCX 解压后总大小最大 60 MB
只允许 PDF / DOCX / TXT
```

校验：

```text
文件扩展名
Content-Type
文件魔数
空文件
空文本
加密 PDF
损坏 ZIP / DOCX
ZIP Bomb
超长文本
```

原则：

```text
不长期保存原始上传文件
只保存解析后的文本和简历版本
临时内容在内存或受控临时目录中处理
```

---

## 5. 解析方案

### PDF

主解析器：

```text
pdfplumber
```

回退：

```text
pypdf
```

策略：

```text
优先提取文本和简单表格
如果主解析文本为空或过短，尝试回退解析
如果最终文本仍为空，返回 scanned_pdf_requires_ocr
```

### DOCX

使用：

```text
python-docx
```

提取：

```text
段落
标题
表格单元格
列表文本
```

### TXT

处理：

```text
按 UTF-8 优先读取
回退常见编码
统一换行和空白
```

### 执行模型

```text
使用 asyncio.to_thread 执行阻塞解析
限制页数和解压大小
不阻塞 FastAPI 事件循环
```

---

## 6. 数据模型

现有：

```text
resumes
resume_versions
resume_versions.source_type
```

当前 `source_type` 约束：

```text
text
pdf
```

需要扩展：

```text
text
pdf
docx
txt
```

可选补充：

```text
original_filename
content_type
file_size
page_count
parsing_status
parsing_error_code
```

第一阶段最小实现只保存：

```text
raw_text
extracted_sections
source_type
```

文件元数据如果加入，必须不包含临时路径和敏感内容。

---

## 7. API 设计

### 上传简历

```http
POST /api/resumes/upload
Content-Type: multipart/form-data
```

字段：

```text
file: 必填
resume_id: 可选，传入时追加新版本
title: 可选，默认取安全化文件名
extract_sections: 可选，默认 true
```

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "resume_id": 1,
    "resume_version_id": 2,
    "source_type": "pdf",
    "char_count": 3500,
    "section_count": 6,
    "preview": "教育经历...",
    "extraction_status": "completed"
  }
}
```

结构化提取失败时：

```text
raw_text 和 resume_version 仍然保存
extraction_status = failed
返回安全错误码
允许后续重试
```

### 简历列表

```http
GET /api/resumes
```

### 简历详情

```http
GET /api/resumes/{resume_id}
```

第一版只做：

```text
当前用户隔离
基础列表
版本基本信息
不返回其他用户数据
```

---

## 8. 错误码

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
resume_not_found
resume_version_conflict
extraction_failed
```

HTTP 映射：

```text
400 / 413 / 415 / 422 / 404
```

---

## 9. 与 RAG 的衔接

上传阶段：

```text
文件
→ 文本
→ resume_version.raw_text
→ 可选 extracted_sections
```

任务运行阶段：

```text
resume_version
→ Chunking
→ FastEmbed
→ Chroma
→ BM25 + 向量召回
→ RRF
→ Rerank
→ EvidencePack
```

不在上传请求中同步完成全部向量索引，避免上传接口过慢。

---

## 10. 文件规划

```text
app/services/resume_file_parser.py
app/services/resume_ingestion.py
app/schemas/resume_upload.py
app/routers/resumes.py
app/repositories/resume.py
tests/test_resume_file_parser.py
tests/test_resume_upload_api.py
docs/RESUME_INGESTION.md
alembic/versions/...resume_source_formats.py
requirements.txt
requirements-dev.txt
```

依赖：

```text
python-multipart
pdfplumber
pypdf
python-docx
reportlab（开发和测试）
```

---

## 11. 分阶段实施

```text
PART 0：设计冻结和分支
PART 1：解析服务和文件校验
PART 2：简历版本持久化
PART 3：上传 API 和最小查询 API
PART 4：结构提取衔接和错误处理
PART 5：测试、文档、Git 和 tag
```

质量门禁：

```text
本 PART 测试不通过，不进入下一 PART
现有 315 条测试必须保持通过
上传功能不能破坏现有 Agent / RAG 主链路
每个 PART 单独 commit
```

---

## 12. 验收标准

```text
文本型 PDF 可以解析并保存
DOCX 可以解析并保存
TXT 可以解析并保存
扫描 PDF 返回 scanned_pdf_requires_ocr
旧版 .doc 返回 unsupported_file_type
损坏和加密 PDF 安全失败
DOCX ZIP Bomb 被拒绝
用户不能访问其他用户简历
可以追加新简历版本
解析后可以创建持久化分析任务
完整测试通过
文档和 Git 闭环完成
```

---

## 13. 完成定义

```text
[x] PART 0：设计与基线
[x] PART 1：解析服务和文件校验
[x] PART 2：简历版本持久化
[x] PART 3：上传 API 和查询 API
[x] PART 4：结构提取衔接
[ ] PART 5：测试、文档和 Git 闭环
```

---

## 14. PART 1 验证记录

新增：

```text
app/services/resume_file_parser.py
tests/test_resume_file_parser.py
app/core/exceptions.py 的 ResumeFileError
```

已支持：

```text
文本型 PDF 解析
DOCX 段落和表格解析
TXT 多种编码解析
PDF 加密检测
扫描 PDF 检测
文件大小限制
PDF 页数限制
文本长度限制
DOCX ZIP Bomb 限制
文件扩展名和魔数校验
```

解析错误码：

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
```

依赖：

```text
python-multipart==0.0.32
pdfplumber==0.11.10
pypdf==6.19.0
python-docx==1.2.0
reportlab==5.0.1（开发测试）
```

验证结果：

```text
解析测试：12 passed
完整测试：338 passed
```

---

## 15. PART 2 验证记录

新增：

```text
app/services/resume_ingestion.py
tests/test_resume_ingestion.py
alembic/versions/4864bd55d0dd_expand_resume_source_formats.py
```

source_type 扩展为：

```text
text
pdf
docx
txt
```

保存规则：

```text
未传 resume_id：创建 Resume + version 1
传入 resume_id：校验用户归属并追加下一个版本
解析文本保存到 resume_version.raw_text
source_type 保存为 pdf / docx / txt
不做文件长期保存
```

验证结果：

```text
简历持久化测试：3 passed
ORM 测试：通过
完整测试：338 passed
Alembic upgrade：4864bd55d0dd
```

---

## 16. PART 3 验证记录

新增接口：

```text
POST /api/resumes/upload
GET  /api/resumes
GET  /api/resumes/{resume_id}
```

上传接口：

```text
multipart/form-data
支持 file / resume_id / title
上传前限制读取大小
解析后保存为简历版本
返回 resume_id、resume_version_id、版本号、字符数和预览
```

查询接口：

```text
只查询当前用户简历
列表返回最新版本摘要
详情返回版本列表
不返回其他用户数据
```

安全：

```text
上传接口接入限流
解析错误使用安全错误码
旧版 .doc 返回 415
不长期保存原始文件
```

验证结果：

```text
上传和查询 API 测试：5 passed
持久化测试：3 passed
完整测试：338 passed
```

---

## 17. PART 4 验证记录

新增：

```text
ResumeExtractionOutcome
extract_resume_sections_safely
上传时可选结构提取
结构提取失败不丢 raw_text
结构提取重试接口
```

上传参数：

```text
extract_sections=true
```

状态：

```text
completed
failed
skipped
```

失败不返回上传失败：

```text
raw_text 和 resume_version 仍然保存
返回 extraction_status=failed
返回安全 extraction_error_code
```

重试接口：

```http
POST /api/resumes/{resume_id}/versions/{resume_version_id}/extract
```

验证结果：

```text
上传和结构提取测试：8 passed
完整测试：338 passed
```
