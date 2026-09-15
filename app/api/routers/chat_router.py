"""客服 HTTP 适配层：接收前端协议并调用项目的应用服务。

在完整链路中，本模块位于最外层：
``前端 -> chat_router -> DialogueService -> DialogueEngine -> 各 Handler``。
它只处理 HTTP/Pydantic 与领域对象之间的格式转换，不应在这里判断意图、推进
任务或直接读写数据库，否则业务逻辑会与 Web 框架耦合。

上游是网页/客户端；下游是 ``api.dependency`` 注入的 ``DialogueService``。
``build_message`` 与 ``build_response`` 是 API 契约和领域契约的连接点：修改字段
时必须同步检查 ``api.schema``、``domain.dialogue_service_domain`` 以及前端。
"""

import uuid
from fastapi import APIRouter, Depends

from app.api.dependency import get_dialogue_service
from app.api.schema import ChatRequest, ChatResponse, HistoryResponse, ChatBotMessage, HistoryMessage, ChatObject
from app.domain.dialogue_service_domain import ProcessResult, Message, MessageType, MessageObject
from app.services.dialogue_service import DialogueService

# 独立 Router 由 api.app 显式挂载，便于以后按业务域拆分更多接口文件。
chat_router = APIRouter()

@chat_router.post("/api/chat")
async def chat(chat_request: ChatRequest,
               dialogue_service: DialogueService = Depends(get_dialogue_service))->ChatResponse:
    """处理一轮用户聊天请求。

    参数:
        chat_request: FastAPI 已校验过的请求体，可能包含纯文本或业务对象；
        dialogue_service: FastAPI 依据依赖链为本请求创建的应用服务。
    返回:
        与当前 message_id 对应的一组机器人消息。

    执行流程:
        API 模型 -> ``build_message`` -> 领域消息 -> Service/Engine 处理
        -> ``ProcessResult`` -> ``build_response`` -> API 响应。

    状态影响:
        本函数自身不改状态；Service 内部会加载 DialogueState，引擎原地修改它，
        然后 Repository 在返回前提交数据库事务。
    """

    # API 的 Pydantic 模型先转换为不依赖 FastAPI 的领域 Message。
    process_resut : ProcessResult = await dialogue_service.process_message(build_message(chat_request))

    # 领域层返回 ProcessResult，再转换成稳定的 HTTP 响应结构。
    return build_response(process_resut)

@chat_router.get("/api/chat/history")
async def history(sender_id: str)->HistoryResponse:
    """返回指定用户的历史消息。

    参数:
        sender_id: URL 查询参数中的用户标识。
    返回:
        ``HistoryResponse``。

    当前限制:
        这里仍是固定演示数据，没有调用 ``DialogueRepository`` 读取真实
        ``DialogueState.session.turns``。因此面试讲解时应明确它是待完善接口，
        不能把这两条消息误认为已实现的历史持久化查询。
    """
    # 当前接口还是演示数据，尚未通过 Repository 读取真实 Session.turns。
    return HistoryResponse(
        sender_id=sender_id,
        messages=[
            HistoryMessage(
                role='user',
                text='hello'
            ),
            HistoryMessage(
                role='bot',
                text='world'
            )
        ]
    )

def build_message(chat_request: ChatRequest)->Message:
    """把外部 ``ChatRequest`` 转换成引擎使用的领域 ``Message``。

    输入:
        chat_request: 已通过 Pydantic 校验的 HTTP 请求模型。
    返回:
        不再依赖 FastAPI/Pydantic 的领域消息。

    关键规则:
        当前用“是否存在 text”决定消息类型；没有 text 就视作对象消息。因此
        ``text`` 与 ``object`` 同时传入时文本优先，而两者都为空时仍会被标成
        OBJECT。若以后加强 API 校验，这里的判定逻辑也要同步。
    """

    return Message(
        # sender_id 用于读取该用户独立的 DialogueState。
        sender_id=chat_request.sender_id,

        # 客户端未提供消息 ID 时由服务端生成，便于请求/响应对应。
        message_id=chat_request.message_id if chat_request.message_id else str(uuid.uuid4()),

        # 当前约定：有 text 就按文本处理，否则按对象处理。
        type=MessageType.TEXT if chat_request.text else MessageType.OBJECT,
        text=chat_request.text,

        # 对象存在时复制为领域 MessageObject，避免领域层依赖 API Schema。
        object=MessageObject(id=chat_request.object.id,
                             type=chat_request.object.type,
                             title=chat_request.object.title,
                             attributes=chat_request.object.attributes
                             ) if chat_request.object else None,
    )


def build_response(process_resut: ProcessResult)->ChatResponse:
    """把领域层结果转换为稳定的 HTTP 响应模型。

    输入:
        process_resut: Engine 对本轮消息的处理结果（参数名保留了原拼写）。
    返回:
        FastAPI 可直接序列化的 ``ChatResponse``。

    数据转换:
        ``BotMessage`` 列表逐项变成 ``ChatBotMessage``；若回复携带商品、订单等
        对象，还要把领域 ``MessageObject`` 再复制成 API ``ChatObject``。
    """
    return ChatResponse(
        sender_id=process_resut.sender_id,
        message_id=process_resut.message_id,
        # 一轮可能产生多条回复，例如“开始任务”后紧接着询问订单号。
        messages=[ChatBotMessage(
            text=message.text,
            object=ChatObject(
                type=message.object.type,
                title=message.object.title,
                attributes=message.object.attributes,
                id=message.object.id
            ) if message.object else None,
        ) for message in process_resut.messages]
    )


