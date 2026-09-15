"""Flow Step 之间三种有向链接的领域模型与 YAML 解析函数。

FlowExecutor 按 next 列表顺序检查链接：Static 直接跳转，Conditional 满足表达式
才跳转，Fallback 兜底。修改链接解析或顺序语义会改变所有 YAML 分支行为。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FlowStepLink:
    """所有链接的基类；target 是下一个 Step 的 id。"""
    target: str


@dataclass(slots=True)
class StaticLink(FlowStepLink):
    """无条件跳转，来源通常是 YAML 中 ``next: step_id``。"""
    @classmethod
    def from_json(cls, data: str) -> "StaticLink":
        """把字符串目标转换为静态链接。"""
        return cls(target=str(data))


@dataclass(slots=True)
class ConditionalLink(FlowStepLink):
    """条件为真时跳往 target；condition 由 FlowExecutor._eval_cond 解释。"""
    condition: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ConditionalLink":
        """把 ``{if: 表达式, then: step_id}`` 转换为条件链接。"""
        return cls(target=str(data["then"]), condition=str(data["if"]))


@dataclass(slots=True)
class FallbackLink(FlowStepLink):
    """前面条件均未命中时使用的 else 兜底链接。"""
    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FallbackLink":
        """把 ``{else: step_id}`` 转换为兜底链接。"""
        return cls(target=str(data["else"]))


def link_from_json(data: str | dict[str, Any]) -> FlowStepLink:
    """根据 YAML next 项的形状选择具体 Link 类型。

    字符串视为 Static；含 if 的字典视为 Conditional；其余字典按 Fallback 解析。
    当前 steps.FlowStep.analyze_next 自行实现了相似逻辑，修改时需同步两处。
    """
    if isinstance(data, str):
        return StaticLink.from_json(data)
    if "if" in data:
        return ConditionalLink.from_json(data)
    return FallbackLink.from_json(data)
