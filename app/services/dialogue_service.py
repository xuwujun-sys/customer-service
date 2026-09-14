
from app.domain.dialogue_service_domain import Message, ProcessResult
from app.domain.dialogue_state import DialogueState
from app.engine.dialogue_engine import DialogueEngine
from app.repository.dialogue_state_repository import DialogueRepository


class DialogueService:
    def __init__(self, dialogue_engine: DialogueEngine
                     , dialogue_repository: DialogueRepository):
        self.dialogue_engine = dialogue_engine
        self.dialogue_repository = dialogue_repository

    async def process_message(self, message: Message) -> ProcessResult:
        #首先加载用户状态
        state: DialogueState = await self.dialogue_repository.load_state(message.sender_id)
        #通过历史状态和最新话题交由dialogue_engine处理
        process_result: ProcessResult = await self.dialogue_engine.process_message(state, message)
        #把最新状态加载入持久层
        await self.dialogue_repository.save_state(state)

        return process_result


