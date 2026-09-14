import json

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.dialogue_state import DialogueState
from app.model.dialogue_state import DialogueStateRecord


class DialogueRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_state(self, sender_id: str)->DialogueState:
        sql = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)
        result = await self.session.execute(sql)
        state = result.scalar_one_or_none()

        if state:
            # state_json字段存的是json字符串，反序列为DialogueState
            dialogue_state: DialogueState = DialogueState.from_dict(json.loads(state.state_json))
            return dialogue_state
        else:
            return DialogueState(sender_id=sender_id)

    async def save_state(self, state: DialogueState):
        state_json: str=json.dumps(state.to_dict())
        insert_stmt = insert(DialogueStateRecord).values(sender_id=state.sender_id,
                                                         state_json=state_json)

        update_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        await self.session.execute(update_stmt)
        await self.session.commit()