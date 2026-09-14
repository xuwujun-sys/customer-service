from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from app.task.flow.steps import (
    CollectSlotStep,
    FlowStep,
    FlowStepType,
    StartFlowStep,
)


@dataclass(slots=True)
class FlowSlot:
    name: str
    type: str = "any"
    label: str = ""
    description: str = ""


@dataclass(slots=True)
class Flow:
    id: str
    description: str = ""
    steps: List[FlowStep] = field(default_factory=list)
    slots: List[FlowSlot] = field(default_factory=list)
    name: str | None = None

    def readable_name(self) -> str:
        return self.name or self.id

    def step_by_id(self, step_id: str | None) -> Optional[FlowStep]:
        if step_id is None:
            return None
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def start_step(self) -> Optional[StartFlowStep]:
        for step in self.steps:
            if isinstance(step, FlowStepType.START):
                return step
        return None

    def collect_steps(self) -> List[CollectSlotStep]:
        return [
            step for step in self.steps if isinstance(step, CollectSlotStep)
        ]

@dataclass(slots=True)
class FlowsList:
    flows: List[Flow] = field(default_factory=list)
    slots: Dict[str, FlowSlot] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Flow]:
        return iter(self.flows)

    def __len__(self) -> int:
        return len(self.flows)

    def flow_by_id(self, flow_id: str) -> Optional[Flow]:
        for flow in self.flows:
            if flow.id == flow_id:
                return flow
        return None

    def slot_by_name(self, slot_name: str) -> Optional[FlowSlot]:
        return self.slots.get(slot_name)
