"""所有业务 Action 必须遵守的抽象接口和统一返回协议。

Flow 只保存动作名称；ActionRegistry 将名称映射到本接口的具体实现；ActionRunner
统一调用 run。具体 Action 可以返回 BotMessage，也可以返回要写回业务任务的槽位，
但不应自行推进 Flow step_id——游标由 FlowExecutor 管理。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState

@dataclass
class ActionResult:
    """Action 的标准结果：可同时携带回复消息和槽位更新。

    ``messages`` 最终汇总进本轮 ProcessResult；``slot_updates`` 由 FlowExecutor
    合并进 active_task.slots，供后续 Action/Response 模板使用。
    """
    messages: list[BotMessage] = field(default_factory=list)
    slot_updates: dict[str, Any] = field(default_factory=dict)


class Action(ABC):
    """可注册动作的抽象基类。

    每个子类必须声明全局唯一 ``name`` 并实现异步 ``run``。Builder 在启动时创建
    实例，Registry 长期持有；Action 实例因此不应保存某个用户的可变状态。
    """
    name: str

    @abstractmethod
    async def run(
        self,
        state: DialogueState,
        action_kwargs: dict[str, Any],
    ) -> ActionResult:
        """执行一次动作。

        参数:
            state: 当前用户完整状态，业务数据通常从 active_task.slots 读取；
            action_kwargs: YAML ActionStep 的 args 经 Executor 解析后的参数。
        返回:
            标准 ActionResult。实现可调用外部服务，但应把结果转成消息/槽位。
        """
        pass
