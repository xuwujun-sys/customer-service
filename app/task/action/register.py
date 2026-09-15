"""Action 名称到 Python 实例的运行时注册表。

它解耦 YAML 与具体类：配置只写 ``action_lookup_order_status``，FlowExecutor 不需
导入该类，ActionRunner 在本注册表中解析名称。新增动作必须成功注册后才可使用。
"""

from typing import Dict

from app.task.action.base import Action


class ActionRegistry:
    """保存进程级共享的 Action 实例，并按唯一名称解析。"""

    def __init__(self) -> None:
        """创建空白名称索引；Builder 随后注册内置和自定义动作。"""
        self._actions: Dict[str, Action] = {}

    def register(self, action: Action) -> None:
        """以 ``action.name`` 注册实例；同名动作会覆盖旧实例。

        当前没有重复名检测，因此命名冲突的行为取决于 Builder 的注册顺序。
        """
        self._actions[action.name] = action

    def get(self, name: str) -> Action:
        """解析动作名；未注册时明确抛错，避免 Flow 被静默跳过。"""
        if name not in self._actions:
            raise KeyError(f"Unknown action '{name}'.")
        return self._actions[name]
