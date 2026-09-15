
"""应用服务层：串起一次完整的客服消息处理事务。

本层不理解用户意图，也不执行具体业务。它只负责协调两个核心组件：
1. DialogueRepository：按用户读取、保存对话状态；
2. DialogueEngine：基于状态处理本轮消息。

因此，一次请求的稳定主线始终是：加载状态 -> 调用引擎 -> 保存状态。
"""

from app.domain.dialogue_service_domain import Message, ProcessResult
from app.domain.dialogue_state import DialogueState
from app.engine.dialogue_engine import DialogueEngine
from app.repository.dialogue_state_repository import DialogueRepository


class DialogueService:
    """协调一次“加载状态—处理消息—保存状态”的应用用例。

    为什么存在:
        Router 不应该知道状态如何持久化，Engine 也不应该知道数据库事务如何
        提交。本类处在两者之间，形成清晰的事务边界。

    创建者与生命周期:
        ``api.dependency.get_dialogue_service`` 为每个 HTTP 请求创建一个实例；
        其中 Engine 是进程共享对象，Repository 只在当前请求中有效。

    协作关系:
        上游为 ``chat_router.chat``；下游为 ``DialogueRepository`` 和
        ``DialogueEngine``。修改处理顺序会直接影响“下一轮能否恢复现场”。
    """

    def __init__(self, dialogue_engine: DialogueEngine
                     , dialogue_repository: DialogueRepository):
        """保存已经由 FastAPI 依赖系统装配好的协作者。

        参数:
            dialogue_engine: 负责规划、Handler 路由与任务推进；
            dialogue_repository: 负责当前请求中的状态读取和事务提交。
        """
        self.dialogue_engine = dialogue_engine
        self.dialogue_repository = dialogue_repository

    async def process_message(self, message: Message) -> ProcessResult:
        """在一个请求内完成一条消息的完整处理。

        参数:
            message: Router 转换好的领域消息，``sender_id`` 是状态查询主键。
        返回:
            Engine 产生的 ``ProcessResult``，供 Router 转换成 HTTP 响应。

        状态与异常:
            Engine 会原地修改加载出的 state。只有 Engine 正常返回后才调用
            ``save_state`` 提交；如果中途抛异常，当前轮不会被保存，避免产生
            “回复失败但步骤已经前进”的半完成状态。
        """

        # HTTP 请求本身不保存上下文，因此先用 sender_id 恢复该用户的“工作现场”。
        state: DialogueState = await self.dialogue_repository.load_state(message.sender_id)

        # 引擎会直接修改 state，例如推进 step、填写 slot、提交本轮消息。
        process_result: ProcessResult = await self.dialogue_engine.process_message(state, message)

        # 将修改后的完整状态写回数据库，让下一次 HTTP 请求可以接着处理。
        await self.dialogue_repository.save_state(state)

        # API 层只关心标准化后的机器人回复，不需要了解内部状态变化。
        return process_result


