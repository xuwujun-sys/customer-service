"""对话服务的输入、输出与消息对象。

【项目位置】
领域层的消息契约，不依赖 FastAPI/Pydantic/SQLAlchemy。API 层在边界处将请求模型
转换为这里的对象，Engine 和 Handler 全程只使用这些领域类型。

【上游调用者】
``chat_router.build_message`` 创建 Message；各 Handler/Action 创建 BotMessage。

【下游使用者】
DialogueEngine、DialogueState、Prompt 历史构建器、API 响应转换和 Repository 序列化。

【联动与修改影响】
新增字段必须同步 ``to_dict/from_dict``、API Schema、chat_router 转换以及历史构造；
否则字段可能在 HTTP 边界或数据库恢复时丢失。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class MessageType(str, Enum):
    """用户消息形态；继承 str 便于 JSON 序列化和接口传输。"""
    TEXT = "text"
    OBJECT = "object"


@dataclass(slots=True)
class MessageObject:
    """用户选中的结构化业务对象。

    职责：携带商品/订单的类型、ID 和展示信息。
    创建者：chat_router 或数据库反序列化逻辑。
    生命周期：随 Message 进入 Turn，随后保存在 Session 历史中。
    协作：DialogueEngine 将它复制为 FocusedObject，并可能映射为 SetSlotsCommand。
    """
    type: str
    id: str
    title: str | None = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转成只包含 JSON 兼容值的字典，供 Turn/DialogueState 持久化。"""
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            # 复制字典，避免调用者修改序列化结果时反向改变领域对象。
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageObject":
        """从数据库 JSON 字典恢复对象；由 Message.from_dict 调用。"""
        return cls(
            type=data["type"],
            id=data["id"],
            title=data.get("title", ""),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass(slots=True)
class Message:
    """进入 DialogueEngine 的标准用户消息。

    message_id 标识本次消息；sender_id 决定加载哪份 DialogueState；type 决定 Engine
    走文本 Planner 还是对象补槽分支。对象的合法组合目前主要由 API 层保证。
    """
    message_id: str
    sender_id: str
    type: MessageType
    text: str | None = None
    object: MessageObject | None = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化用户消息，最终嵌入 Turn 和 DialogueState JSON。"""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            # Enum 必须取 value，json.dumps 之后才能稳定恢复为 MessageType。
            "type": self.type.value,
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从持久化字典恢复 Message 及其可选 MessageObject。"""

        return cls(
            message_id=data["message_id"],
            sender_id=data["sender_id"],
            # 非法 type 在这里尽早抛 ValueError，避免 Engine 进入未知分支。
            type=MessageType(data["type"]),
            text=data["text"],
            object=MessageObject.from_dict(data["object"]) if data["object"] is not None else None,
        )


@dataclass(slots=True)
class BotMessage:
    """机器人产生的一条输出。

    Handler 返回 ``list[BotMessage]``，Engine 将其加入 pending_turn，API 再转换为
    ChatBotMessage。同一轮可能产生任务确认和槽位追问等多条消息。
    """
    text: str | None = None
    object: MessageObject | None = None

    def to_dict(self) -> Dict[str, Any]:
        """为会话历史持久化生成 JSON 兼容字典。"""
        return {
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotMessage":
        """恢复历史机器人消息及其可选对象。"""
        raw_object = data.get("object")
        return cls(
            text=data.get("text"),
            object=MessageObject.from_dict(raw_object) if raw_object is not None else None,
        )


@dataclass(slots=True)
class ProcessResult:
    """DialogueEngine 返回给 Service/API 的本轮处理结果。

    它不包含完整 DialogueState；状态由引用原地修改并由 Repository 单独保存。
    sender_id/message_id 让前端能够把多用户、多请求响应正确关联。
    """
    sender_id: str
    message_id: str
    messages: List[BotMessage] = field(default_factory=list)
