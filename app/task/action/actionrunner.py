"""Action 调用描述与统一运行入口。

FlowExecutor 只产生 ActionCall；本模块将名字解析为已注册 Action 并异步运行。
它是工作流解释器与订单/物流等业务实现之间的稳定边界。
"""

from typing import Any
from dataclasses import dataclass, field

from app.domain.dialogue_state import DialogueState
from app.task.action.base import ActionResult
from app.task.action.register import ActionRegistry


@dataclass
class ActionCall:
    """FlowExecutor 生成的瞬时动作请求，不包含用户状态本身。

    action_name 来自 YAML；action_kwargs 来自 ActionStep.args 或 context 字段。
    """
    action_name: str
    action_kwargs: dict[str, Any] = field(default_factory=dict)


class ActionRunner:
    """根据动作名解析并统一异步执行 Action。

    由 Builder 创建，随后注入 TaskHandler；自身只持有只读式 Registry，不保存
    用户数据，可以跨请求复用。
    """

    def __init__(
        self,
        registry: ActionRegistry,
    ) -> None:
        """绑定启动阶段已填充的动作注册表。"""
        self.registry = registry

    async def run(
        self,
        action_call: ActionCall,
        state: DialogueState,
    ) -> ActionResult:
        """解析一个 ActionCall，并将当前状态和参数交给具体动作。

        未知 action_name 会由 Registry 抛 KeyError；具体动作的网络/业务异常应由
        动作自己转换成合适的 ActionResult，或继续向上抛使本轮不提交。
        """
        # YAML 只存 action_name，真实 Python 对象由 Registry 解耦查找。
        action_name = action_call.action_name
        action = self.registry.get(action_name)

        # ActionResult 可以同时返回机器人消息和需要写回的槽位。
        return await action.run(state, action_call.action_kwargs)
