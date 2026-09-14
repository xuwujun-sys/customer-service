from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FlowStepLink:
    target: str


@dataclass(slots=True)
class StaticLink(FlowStepLink):
    @classmethod
    def from_json(cls, data: str) -> "StaticLink":
        return cls(target=str(data))


@dataclass(slots=True)
class ConditionalLink(FlowStepLink):
    condition: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ConditionalLink":
        return cls(target=str(data["then"]), condition=str(data["if"]))


@dataclass(slots=True)
class FallbackLink(FlowStepLink):
    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FallbackLink":
        return cls(target=str(data["else"]))


def link_from_json(data: str | dict[str, Any]) -> FlowStepLink:
    if isinstance(data, str):
        return StaticLink.from_json(data)
    if "if" in data:
        return ConditionalLink.from_json(data)
    return FallbackLink.from_json(data)
