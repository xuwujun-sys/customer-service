import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.contexts import SystemContext, TaskContext
from app.domain.dialogue_service_domain import BotMessage, Message

@dataclass
class FocusedObject:
    type: str
    id: str
    title: str | None = None
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        return cls(**data)

@dataclass
class Turn:
    turn_id: str
    user_message: Message
    bot_messages: list[BotMessage]

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message.to_dict(),
            "bot_messages": [message.to_dict() for message in self.bot_messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        return cls(
            turn_id=data["turn_id"],
            user_message=Message.from_dict(data["user_message"]),
            bot_messages=[BotMessage.from_dict(message) for message in data["bot_messages"]],
        )

@dataclass
class Session:
    session_id: str
    started_at: float
    last_activity_at: float
    turns: list[Turn] = field(default_factory=list)
    closed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "turns": [turn.to_dict() for turn in self.turns],
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            last_activity_at=data["last_activity_at"],
            turns=[Turn.from_dict(turn) for turn in data["turns"]],
            closed_at=data["closed_at"],
        )

@dataclass
class DialogueState:
    sender_id: str
    active_task: TaskContext | None = None
    paused_tasks: list[TaskContext] = field(default_factory=list)
    active_system_task: SystemContext | None = None
    focused_object: FocusedObject | None = None
    sessions: list[Session] = field(default_factory=list)
    current_session_id: str | None = None
    pending_turn: Turn | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "active_task": self.active_task.to_dict() if self.active_task else None,
            "paused_tasks": [task.to_dict() for task in self.paused_tasks],
            "active_system_task": self.active_system_task.to_dict() if self.active_system_task else None,
            "focused_object": self.focused_object.to_dict() if self.focused_object else None,
            "sessions": [session.to_dict() for session in self.sessions],
            "current_session_id": self.current_session_id,
            "pending_turn": self.pending_turn.to_dict() if self.pending_turn else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any])-> "DialogueState":
        return cls(
            sender_id=data["sender_id"],
            active_task=TaskContext.from_dict(data["active_task"]) if data["active_task"] else None,
            paused_tasks=[TaskContext.from_dict(task) for task in data["paused_tasks"]],
            active_system_task=SystemContext.from_dict(data["active_system_task"]) if data["active_system_task"] else None,
            focused_object=FocusedObject.from_dict(data["focused_object"]) if data["focused_object"] else None,
            sessions=[Session.from_dict(session) for session in data["sessions"]],
            current_session_id=data["current_session_id"],
            pending_turn=Turn.from_dict(data["pending_turn"]) if data["pending_turn"] else None,
        )

    def end_system_task(self) -> None:
        self.active_system_task = None

    def pause_active_task(self) -> None:
        if self.active_task:
            self.paused_tasks.append(self.active_task)
            self.active_task = None

    def start_new_task(self, task:TaskContext)->None:
        self.active_task = task

    def start_new_system_task(self, system_task:SystemContext)->None:
        self.active_system_task = system_task

    def cancel_active_task(self) -> None:
        self.active_task = None

    def match_task_to_resume(self, flow_id: str) -> TaskContext | None:
        for task in self.paused_tasks:
            if task.flow_id == flow_id:
                return task
        return None

    def set_slots(self, slots: dict[str, Any]) -> None:
        self.active_task.slots.update(slots)

    def current_task(self):
        return self.active_system_task or self.active_task

    def remove_active_task_slots(self, slot_name):
        self.active_task.slots.pop(slot_name)

    def end_user_task(self):
        self.active_task = None

    def current_session(self)->Session | None:
        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session
        return None

    def start_session(self):
        now = time.time()
        session = Session(
            session_id=str(uuid.uuid4()),
            started_at=now,
            last_activity_at=now,
        )
        self.sessions.append(session)
        self.current_session_id = session.session_id

    def close_current_session(self):
        self.current_session().closed_at = time.time()
        self.current_session_id = None

    def reset_runtime_state_for_new_session(self):
        self.active_task = None
        self.active_system_task = None
        self.focused_object = None
        self.paused_tasks = []

    def begin_turn(self, message: Message):
        self.pending_turn = Turn(
            turn_id=str(uuid.uuid4()),
            user_message=message,
            bot_messages=[],
        )

    def commit_pending_turn(self):
        self.current_session().turns.append(self.pending_turn)
        self.pending_turn = None

    def set_focused_object(self, param):
        self.focused_object = param


if __name__ == "__main__":
    import asyncio
    import time

    from app.domain.contexts import TaskContext, SystemContext
    from app.domain.dialogue_service_domain import Message, BotMessage, MessageType, MessageObject
    from app.domain.dialogue_state import (
        DialogueState, FocusedObject, Session, Turn,
    )
    from app.infrastructure import database as db
    from app.repository.dialogue_state_repository import DialogueRepository


    async def test():
        db.init_db_engine()
        async with db.session_factory() as session:
            rp = DialogueRepository(session)

            now = time.time()

            state = DialogueState(
                sender_id="test_user_001",

                # 进行中的任务 + 挂起的任务
                active_task=TaskContext(
                    flow_id="order",
                    step_id="confirm",
                    slots={"item": "laptop", "qty": 1},
                ),
                paused_tasks=[
                    TaskContext(flow_id="refund", step_id="reason"),
                    TaskContext(flow_id="cancel", step_id="check_eligibility", slots={"order_id": "o-2026-001"}),
                ],

                # 系统级任务（问候、引导等）
                active_system_task=SystemContext(flow_id="greeting", step_id="welcome"),

                # 当前聚焦对象
                focused_object=FocusedObject(
                    type="product",
                    id="p1001",
                    title="MacBook Pro 14",
                    attributes={"price": 14999, "color": "silver"},
                ),

                # 会话历史
                sessions=[
                    Session(
                        session_id="s1",
                        started_at=now - 3600,
                        last_activity_at=now - 60,
                        closed_at=now - 1800,
                        turns=[
                            Turn(
                                turn_id="t1",
                                user_message=Message(
                                    message_id="m1",
                                    sender_id="test_user_001",
                                    type=MessageType.TEXT,
                                    text="我想买个电脑",
                                ),
                                bot_messages=[
                                    BotMessage(text="好的，请问预算多少？"),
                                ],
                            ),
                            Turn(
                                turn_id="t2",
                                user_message=Message(
                                    message_id="m2",
                                    sender_id="test_user_001",
                                    type=MessageType.OBJECT,
                                    text="这个怎么样",
                                    object=MessageObject(type="product", id="p1001", title="MacBook Pro 14"),
                                ),
                                bot_messages=[
                                    BotMessage(
                                        object=MessageObject(type="product", id="p1001", title="MacBook Pro 14")),
                                ],
                            ),
                        ],
                    ),
                ],

                # 当前会话
                current_session_id="s1",

                # 待回复的一轮（没有就先 None）
                pending_turn=None,
            )

            await rp.save_state(state)
            res = await rp.load_state("test_user_001")
            print(res)

        await db.close_db_engine()


    asyncio.run(test())









