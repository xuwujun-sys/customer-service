"""Flow 中各种 Step 节点的强类型定义及 YAML 字典转换规则。

FlowLoader 依据 ``step.type`` 从 mapping_types 选择子类；FlowExecutor 再依据实例
类型决定如何解释节点。这里新增/修改一种 Step，必须同步检查 Loader 映射、
Executor._run_step 分派以及 YAML 字段格式。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Any

from app.task.flow.links import (
    FlowStepLink,
    link_from_json, ConditionalLink, FallbackLink, StaticLink,
)


class FlowStepType(str, Enum):
    """YAML 允许声明的 Step 类型枚举，也是 mapping_types 的键。"""
    START = "start"
    ACTION = "action"
    COLLECT = "collect"
    SET_SLOTS = "set_slots"
    END = "end"


@dataclass(slots=True)
class ResponseDefinition:
    """Flow 配置中的回复定义，可为静态 text 或由 prompt 动态生成。"""
    mode: str = "static"
    text: str | None = None
    prompt: str | None = None


@dataclass(slots=True)
class SlotValidation:
    """Collect 节点的可选校验：条件不成立时使用 failure_response。"""
    condition: str | None = None
    failure_response: ResponseDefinition | None = None


@dataclass(slots=True)
class FlowStep:
    """所有流程节点共享的结构。

    id 是 TaskContext.step_id 指向的稳定游标；next 是已经解析好的链接列表；
    description 只解释节点用途，不参与执行。
    """
    id: str
    type: FlowStepType
    next: List[FlowStepLink] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]):
        """提取所有 Step 共用字段，供具体子类通过 ``**`` 复用。

        虽名为 from_dict，本基类返回的是公共参数 dict，而不是 FlowStep 实例；
        具体子类负责补自己的字段并真正构造对象。
        """
        return {
            "id" : str(stepdata["id"]),
            "description":stepdata.get("description", ""),
            "type":FlowStepType(stepdata["type"]),
            "next":FlowStep.analyze_next(stepdata["next"]),
        }

    @staticmethod
    def analyze_next(ori_next:list[dict[str, str]] | str)->list[FlowStepLink]:
        """将 YAML 的字符串或条件列表转换成按顺序执行的 Link 对象。

        列表顺序会被 Executor 保留；每项应含 if/then 或 else。静态字符串则只
        产生一个 StaticLink。
        """
        next=[]
        if isinstance(ori_next, list):
            for val in ori_next:
                if "if" in val:
                    next.append(ConditionalLink(condition=val["if"],target=val["then"]))
                elif "else" in val:
                    next.append(FallbackLink(target=val["else"]))
        else:
            next.append(StaticLink(target=ori_next))

        return next


@dataclass(slots=True)
class StartFlowStep(FlowStep):
    """Flow 唯一入口节点；Executor 只负责立即跳到 next。"""
    type: FlowStepType = FlowStepType.START

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "StartFlowStep":
        """由公共字段构造 StartFlowStep。"""
        return cls(
            **FlowStep.from_dict(stepdata),
        )


@dataclass(slots=True)
class ActionFlowStep(FlowStep):
    """请求执行某个已注册 Action 的节点。

    action 必须与 Action.name 完全一致；args 可为静态 dict 或 context.xxx 引用。
    """
    type: FlowStepType = FlowStepType.ACTION
    action: str = ""
    args: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "ActionFlowStep":
        """读取动作名和可选参数，并构造 ActionFlowStep。"""
        return cls(
            **FlowStep.from_dict(stepdata),
            action=stepdata["action"],
            args=stepdata.get("args",{})
        )


@dataclass(slots=True)
class CollectSlotStep(FlowStep):
    """确保 active_task.slots 中存在指定槽位的收集节点。

    缺值时 FlowExecutor 不移动当前业务游标，而是创建系统收集任务；有值时可先
    执行 validation，再跳到 next。
    """
    type: FlowStepType = FlowStepType.COLLECT
    slot_name: str = ""
    response: ResponseDefinition = field(default_factory=ResponseDefinition)
    validation: Optional[SlotValidation] = None

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "CollectSlotStep":
        """解析槽位名、询问回复以及可选校验配置。"""
        return cls(
            **FlowStep.from_dict(stepdata),
            slot_name=stepdata["slot_name"],
            response=ResponseDefinition(**stepdata["response"]),
            validation=SlotValidation(condition=stepdata["validation"]["condition"],
            failure_response=ResponseDefinition(**stepdata["validation"]["failure_response"]))
            if stepdata.get("validation",None) else None
        )


@dataclass(slots=True)
class SetSlotsFlowStep(FlowStep):
    """声明式设置槽位节点。

    当前虽已加入 mapping_types，但没有独立 from_dict，FlowExecutor._run_step 也
    没有处理该类型；YAML 若实际使用它将无法正常执行。这是尚未闭环的扩展点。
    """
    type: FlowStepType = FlowStepType.SET_SLOTS
    slots: List[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EndFlowStep(FlowStep):
    """流程终点；Executor 根据当前上下文结束系统任务或用户任务。"""
    type: FlowStepType = FlowStepType.END

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "EndFlowStep":
        """由公共字段构造 EndFlowStep。"""
        return cls(
            **FlowStep.from_dict(stepdata),
        )

# Loader 使用的类型工厂表；键同时接受 FlowStepType（它继承 str）对应的 YAML 值。
mapping_types = {
    FlowStepType.START: StartFlowStep,
    FlowStepType.ACTION: ActionFlowStep,
    FlowStepType.COLLECT: CollectSlotStep,
    FlowStepType.SET_SLOTS: SetSlotsFlowStep,
    FlowStepType.END: EndFlowStep,
}
