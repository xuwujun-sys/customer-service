from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Any

from app.task.flow.links import (
    FlowStepLink,
    link_from_json, ConditionalLink, FallbackLink, StaticLink,
)


class FlowStepType(str, Enum):
    START = "start"
    ACTION = "action"
    COLLECT = "collect"
    SET_SLOTS = "set_slots"
    END = "end"


@dataclass(slots=True)
class ResponseDefinition:
    mode: str = "static"
    text: str | None = None
    prompt: str | None = None


@dataclass(slots=True)
class SlotValidation:
    condition: str | None = None
    failure_response: ResponseDefinition | None = None


@dataclass(slots=True)
class FlowStep:
    id: str
    type: FlowStepType
    next: List[FlowStepLink] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]):
        return {
            "id" : str(stepdata["id"]),
            "description":stepdata.get("description", ""),
            "type":FlowStepType(stepdata["type"]),
            "next":FlowStep.analyze_next(stepdata["next"]),
        }

    @staticmethod
    def analyze_next(ori_next:list[dict[str, str]] | str)->list[FlowStepLink]:
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
    type: FlowStepType = FlowStepType.START

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "StartFlowStep":
        return cls(
            **FlowStep.from_dict(stepdata),
        )


@dataclass(slots=True)
class ActionFlowStep(FlowStep):
    type: FlowStepType = FlowStepType.ACTION
    action: str = ""
    args: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "ActionFlowStep":
        return cls(
            **FlowStep.from_dict(stepdata),
            action=stepdata["action"],
            args=stepdata.get("args",{})
        )


@dataclass(slots=True)
class CollectSlotStep(FlowStep):
    type: FlowStepType = FlowStepType.COLLECT
    slot_name: str = ""
    response: ResponseDefinition = field(default_factory=ResponseDefinition)
    validation: Optional[SlotValidation] = None

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "CollectSlotStep":
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
    type: FlowStepType = FlowStepType.SET_SLOTS
    slots: List[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EndFlowStep(FlowStep):
    type: FlowStepType = FlowStepType.END

    @classmethod
    def from_dict(cls, stepdata: Dict[str, Any]) -> "EndFlowStep":
        return cls(
            **FlowStep.from_dict(stepdata),
        )

mapping_types = {
    FlowStepType.START: StartFlowStep,
    FlowStepType.ACTION: ActionFlowStep,
    FlowStepType.COLLECT: CollectSlotStep,
    FlowStepType.SET_SLOTS: SetSlotsFlowStep,
    FlowStepType.END: EndFlowStep,
}