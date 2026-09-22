# 定义当前用户的数据结构。

from pydantic import BaseModel


# 表示后端鉴权后确认的当前用户。
class CurrentUser(BaseModel):
    id: int
    username: str
    role: str