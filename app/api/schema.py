"""客服 HTTP 接口的 Pydantic 数据契约。

【项目位置】
位于 API 边界层，只描述前端可以发送/接收的 JSON 形状。领域层使用的是
``app.domain.dialogue_service_domain`` 中的 dataclass，两者由 chat_router 转换。

【上游调用者】
FastAPI 根据这些模型校验请求体并生成接口响应/OpenAPI 文档。

【下游依赖】
``chat_router.build_message`` 将 ChatRequest/ChatObject 转成 Message/MessageObject；
``chat_router.build_response`` 将 ProcessResult 转回 ChatResponse。

【联动与修改影响】
修改消息字段时必须同步检查 chat_router、领域消息模型、DialogueState 序列化和
历史消息构造。特别是 ``type/id`` 会继续参与 focused_object 与对象补槽判断。
"""

from pydantic import BaseModel


class ChatObject(BaseModel):
    """前后端传递的商品或订单对象。

    ``type`` 当前约定为 product/order，``id`` 会在对象消息中映射为
    product_id/order_number；attributes 用于携带不参与核心路由的扩展信息。
    该对象由 Pydantic 按请求创建，生命周期通常只覆盖一次 HTTP 请求/响应。
    """
    type: str
    id: str
    title: str | None = None
    attributes: dict = {}


class ChatRequest(BaseModel):
    """POST /api/chat 的请求体。

    sender_id 用于加载用户 DialogueState；message_id 可由客户端提供以追踪请求；
    text 与 object 表示两种消息形态。当前代码尚未校验二者至少有一个。
    """
    sender_id: str
    message_id: str | None = None
    text: str | None = None
    object: ChatObject | None = None

class ChatBotMessage(BaseModel):
    """一条机器人输出；一次响应可能包含多条此对象。"""
    text: str | None = None
    object: ChatObject | None = None


class ChatResponse(BaseModel):
    """POST /api/chat 的响应体，与本次用户消息通过 message_id 关联。"""
    sender_id: str
    message_id: str
    messages: list[ChatBotMessage]

class HistoryMessage(BaseModel):
    """历史接口中的单条消息；role 区分 user 与 bot。"""
    role: str
    text: str | None = None
    object: ChatObject | None = None

class HistoryResponse(BaseModel):
    """GET /api/chat/history 的响应体；当前路由仍返回演示数据。"""
    sender_id: str
    messages: list[HistoryMessage]
