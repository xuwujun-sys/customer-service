from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class TaskContext:
    flow_id: str
    step_id: str | None = None
    slots: dict = field(default_factory=dict)

    def to_dict(self)->dict[str, Any]:
        return {
            'flow_id': self.flow_id,
            'step_id': self.step_id,
            'slots': self.slots
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any])->"TaskContext":
        return cls(**data)

@dataclass
class SystemContext:
    flow_id: str
    step_id: str | None = None

    def to_dict(self)->dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any])->"SystemContext":
        clz = mapping_types[data["flow_id"]]
        return clz(**data)

@dataclass
class StartedSystemContext(SystemContext):
    started_flow_id: str = ""
    started_flow_name: str = ""


@dataclass
class InterruptedSystemContext(SystemContext):
    interrupted_flow_id: str = ""
    interrupted_flow_name: str = ""
    started_flow_id: str = ""
    started_flow_name: str = ""

@dataclass
class CanceledSystemContext(SystemContext):
    canceled_flow_id: str = ""
    canceled_flow_name: str = ""

@dataclass
class ResumedSystemContext(SystemContext):
    resumed_flow_id: str = ""
    resumed_flow_name: str = ""

@dataclass
class CollectSystemContext(SystemContext):
    slot_name: str = ""
    response: dict[str, Any] = field(default_factory=dict)

mapping_types = {
    "system_task_started": StartedSystemContext,
    "system_task_interrupted": InterruptedSystemContext,
    "system_task_canceled": CanceledSystemContext,
    "system_task_resumed": ResumedSystemContext,
    "system_collect_information": CollectSystemContext,
}