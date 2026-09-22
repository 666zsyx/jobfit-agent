# 提供统一的成功响应结构。

from fastapi.encoders import jsonable_encoder


# 包装成功响应，并递归转换 Pydantic 等不可直接 JSON 化的对象。
def success_response(message: str = "success", data=None) -> dict:
    return {
        "code": 200,
        "message": message,
        "data": jsonable_encoder(data),
    }