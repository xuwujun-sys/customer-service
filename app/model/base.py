"""SQLAlchemy 声明式模型基类。

所有 ORM 表模型应继承 Base，使 SQLAlchemy 能把它们收集到同一份 metadata。
当前仅被 DialogueStateRecord 使用；若引入迁移工具，也会依赖 Base.metadata。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """项目 ORM 模型的共同基类，由 SQLAlchemy 在类定义阶段读取。"""
    pass
