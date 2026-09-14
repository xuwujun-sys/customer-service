from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Command:
    command: str

    @staticmethod
    def from_dict(data: Dict[str, Any]):
        cls = mapping_types[data["command"]]
        return cls(**data)

@dataclass
class StartFlowCommand(Command):
    flow: str

@dataclass
class SetSlotsCommand(Command):
    slots: dict[str, Any]


@dataclass
class CancelFlowCommand(Command):
    pass


@dataclass
class ResumeFlowCommand(Command):
    flow: str

mapping_types = {
    "start_flow": StartFlowCommand,
    "set_slots": SetSlotsCommand,
    "cancel_flow": CancelFlowCommand,
    "resume_flow": ResumeFlowCommand,
}