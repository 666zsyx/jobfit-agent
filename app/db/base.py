# 定义所有 ORM 模型共享的声明式 Base。

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """JobFit ORM 模型的统一基类。"""
