"""DialogueState 对应的数据库表模型。

【上游】DialogueRepository 使用该类生成 SELECT 和 MySQL UPSERT。
【下游】SQLAlchemy 根据字段定义访问 dialogue_states 表。
【联动】sender_id 必须与 Message.sender_id/DialogueState.sender_id 含义一致；state_json
必须能容纳 DialogueState.to_dict 的完整 JSON。修改列名需同步数据库迁移与 Repository。
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.model.base import Base


class DialogueStateRecord(Base):
    """一名用户一行的对话状态记录。

    ORM 实例只在一次数据库 Session 查询中存在；它不是业务状态本身，Repository 会
    把 ``state_json`` 反序列化成领域层 DialogueState 后再交给 Engine。
    """

    __tablename__ = "dialogue_states"

    # 主键保证同一用户只有一份最新状态，也是 MySQL upsert 的冲突判断依据。
    sender_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # 使用 Text 保存聚合状态，便于教学项目整体恢复；代价是不方便按内部字段查询。
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
