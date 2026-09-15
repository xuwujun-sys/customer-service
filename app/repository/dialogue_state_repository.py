"""DialogueState 的 MySQL 持久化仓库。

当前采用“一名用户一行、完整状态一个 JSON”的教学型设计，使任务进度、
聚焦对象和会话历史能够跨无状态 HTTP 请求恢复。
"""

import json

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.dialogue_state import DialogueState
from app.model.dialogue_state import DialogueStateRecord


class DialogueRepository:
    """以 JSON 快照方式持久化每位用户的完整 ``DialogueState``。

    为什么存在:
        领域层只操作 Python 对象，不关心 SQLAlchemy、MySQL 方言或事务；所有
        映射细节集中在本类，未来换 Redis/文档数据库时上层调用方式可以不变。

    创建者与生命周期:
        FastAPI 的 ``get_repository`` 每个请求创建一次，持有同请求的
        ``AsyncSession``，请求结束后一起销毁。

    协作关系:
        上游是 ``DialogueService``；下游是 ORM 模型 ``DialogueStateRecord``，
        并依赖 ``DialogueState.to_dict/from_dict`` 的序列化契约。领域状态新增字段
        时，必须保证那两个方法同步更新，否则数据库快照会丢字段或无法恢复。
    """

    def __init__(self, session: AsyncSession):
        """绑定当前请求独占的异步数据库 Session。"""
        self.session = session

    async def load_state(self, sender_id: str)->DialogueState:
        """按 ``sender_id`` 恢复用户工作现场。

        参数:
            sender_id: 客户端用户标识，也是表 ``dialogue_states`` 的主键。
        返回:
            有记录时返回反序列化状态；首次对话则返回只含 sender_id 的新状态。

        执行流程:
            构造 SELECT -> 异步执行 -> 至多取一行 -> JSON 解码 -> 领域对象重建。
        本函数只读取，不修改数据库，也不提交事务。
        """

        # sender_id 是 dialogue_states 表主键。
        sql = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)
        result = await self.session.execute(sql)
        # 主键查询理论上最多一行；scalar_one_or_none 还能暴露异常重复数据。
        state = result.scalar_one_or_none()

        if state:
            # JSON 先转为 dict，再递归恢复 Session、Turn、TaskContext 等对象。
            dialogue_state: DialogueState = DialogueState.from_dict(json.loads(state.state_json))
            return dialogue_state
        else:
            # 新用户没有数据库记录，只需要 sender_id，其余字段使用默认值。
            return DialogueState(sender_id=sender_id)

    async def save_state(self, state: DialogueState):
        """将内存中的完整状态快照以 upsert 方式写入 MySQL。

        参数:
            state: Engine 已完成本轮修改的 ``DialogueState``。
        返回:
            无业务返回值；成功后事务已经提交。

        为什么使用 upsert:
            第一次对话需要 INSERT，后续轮次需要 UPDATE；以 sender_id 为唯一键
            的单条语句同时覆盖两种情况，避免先查询再决定写法产生竞态窗口。

        修改影响:
            当前是“整份 JSON 覆盖”，实现简单但并发处理同一 sender_id 时可能
            后写覆盖先写。若项目未来支持同用户并发请求，需要在此引入版本号、
            行锁或乐观锁，而不是只改 Engine。
        """

        # 领域对象递归转 dict，再序列化为数据库 Text 字段。
        state_json: str=json.dumps(state.to_dict())
        insert_stmt = insert(DialogueStateRecord).values(sender_id=state.sender_id,
                                                         state_json=state_json)

        # 主键已存在时更新 JSON，使同一 sender_id 始终只有一行。
        update_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        await self.session.execute(update_stmt)

        # 请求成功处理后的状态在这里正式提交到数据库。
        await self.session.commit()
