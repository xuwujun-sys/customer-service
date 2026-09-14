import uuid
from fastapi import APIRouter, Depends

from app.api.dependency import get_dialogue_service
from app.api.schema import ChatRequest, ChatResponse, HistoryResponse, ChatBotMessage, HistoryMessage, ChatObject
from app.domain.dialogue_service_domain import ProcessResult, Message, MessageType, MessageObject
from app.services.dialogue_service import DialogueService

chat_router = APIRouter()

@chat_router.post("/api/chat")
async def chat(chat_request: ChatRequest,
               dialogue_service: DialogueService = Depends(get_dialogue_service))->ChatResponse:
    process_resut : ProcessResult = await dialogue_service.process_message(build_message(chat_request))
    return build_response(process_resut)

@chat_router.get("/api/chat/history")
async def history(sender_id: str)->HistoryResponse:
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

    return Message(
        sender_id=chat_request.sender_id,
        message_id=chat_request.message_id if chat_request.message_id else str(uuid.uuid4()),
        type=MessageType.TEXT if chat_request.text else MessageType.OBJECT,
        text=chat_request.text,
        object=MessageObject(id=chat_request.object.id,
                             type=chat_request.object.type,
                             title=chat_request.object.title,
                             attributes=chat_request.object.attributes
                             ) if chat_request.object else None,
    )


def build_response(process_resut: ProcessResult)->ChatResponse:
    return ChatResponse(
        sender_id=process_resut.sender_id,
        message_id=process_resut.message_id,
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


