from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class MessageType(str, Enum):
    TEXT = "text"
    OBJECT = "object"


@dataclass(slots=True)
class MessageObject:
    type: str
    id: str
    title: str | None = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageObject":
        return cls(
            type=data["type"],
            id=data["id"],
            title=data.get("title", ""),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass(slots=True)
class Message:
    message_id: str
    sender_id: str
    type: MessageType
    text: str | None = None
    object: MessageObject | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "type": self.type.value,
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":

        return cls(
            message_id=data["message_id"],
            sender_id=data["sender_id"],
            type=MessageType(data["type"]),
            text=data["text"],
            object=MessageObject.from_dict(data["object"]) if data["object"] is not None else None,
        )


@dataclass(slots=True)
class BotMessage:
    text: str | None = None
    object: MessageObject | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotMessage":
        raw_object = data.get("object")
        return cls(
            text=data.get("text"),
            object=MessageObject.from_dict(raw_object) if raw_object is not None else None,
        )


@dataclass(slots=True)
class ProcessResult:
    sender_id: str
    message_id: str
    messages: List[BotMessage] = field(default_factory=list)
