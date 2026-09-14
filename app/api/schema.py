from pydantic import BaseModel


class ChatObject(BaseModel):
    type: str
    id: str
    title: str | None = None
    attributes: dict = {}


class ChatRequest(BaseModel):
    sender_id: str
    message_id: str | None = None
    text: str | None = None
    object: ChatObject | None = None

class ChatBotMessage(BaseModel):
    text: str | None = None
    object: ChatObject | None = None


class ChatResponse(BaseModel):
    sender_id: str
    message_id: str
    messages: list[ChatBotMessage]

class HistoryMessage(BaseModel):
    role: str
    text: str | None = None
    object: ChatObject | None = None

class HistoryResponse(BaseModel):
    sender_id: str
    messages: list[HistoryMessage]