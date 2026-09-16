from pydantic import BaseModel


class CurrentUser(BaseModel):
    id: int
    username: str
    role: str