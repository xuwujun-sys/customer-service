"""工作流“等待用户输入”的哨兵 Action 定义。

FlowExecutor 看到名为 ``action_listen`` 的 ActionCall 时会直接停止本轮循环，实际
不会调用本类的 run。所谓暂停不是本方法阻塞，而是 Executor 返回、Repository
保存当前 step/slots，等待下一次 HTTP 请求再次进入。
"""

from typing import Any
from app.domain.dialogue_state import DialogueState
from app.task.action.base import Action, ActionResult

class ActionListen(Action):
    """标识运行边界的内置动作；名称与 Executor 的判断字符串联动。"""
    name = 'action_listen'
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """理论上的接口占位；正常执行路径不会调用，因此没有 ActionResult。"""
        pass
