"""对话状态聚合根：保存一个用户可恢复的完整对话现场。

DialogueState 同时承载：
- 当前/暂停的用户任务；
- 优先执行的系统辅助任务；
- 当前聚焦的商品或订单；
- Session、历史 Turn 与正在处理的 pending_turn。

Repository 会把它整体序列化为 JSON，下一次请求再完整恢复。
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.contexts import SystemContext, TaskContext
from app.domain.dialogue_service_domain import BotMessage, Message

@dataclass
class FocusedObject:
    """前端当前选中的商品或订单，用于指代和自动补槽。

    创建者：DialogueEngine 处理 OBJECT Message 时创建，或 from_dict 从数据库恢复。
    生命周期：在同一 Session 内持续存在，新对象会覆盖旧对象；Session 超时后清空。
    协作：Planner 用它解析“这个”，Validator 检查 Knowledge required_object，
    FlowExecutor/DialogueEngine 用它自动填 product_id 或 order_number。
    """
    type: str
    id: str
    title: str | None = None
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为可持久化字典；字段同时与 MessageObject/ChatObject 保持语义一致。"""
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """从 DialogueState JSON 恢复聚焦对象。"""
        return cls(**data)

@dataclass
class Turn:
    """一轮用户输入及其对应的全部机器人回复。

    创建者：DialogueState.begin_turn。
    生命周期：先作为 pending_turn，成功处理后进入 Session.turns 并随状态持久化。
    协作：BuildHistory 将已提交 Turn 转为 Prompt 历史；当前 pending_turn 单独作为最新输入。
    """
    turn_id: str
    user_message: Message
    bot_messages: list[BotMessage]

    def to_dict(self) -> dict[str, Any]:
        """递归序列化 Message 和全部 BotMessage。"""
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message.to_dict(),
            "bot_messages": [message.to_dict() for message in self.bot_messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """恢复完整一轮历史；由 Session.from_dict 调用。"""
        return cls(
            turn_id=data["turn_id"],
            user_message=Message.from_dict(data["user_message"]),
            bot_messages=[BotMessage.from_dict(message) for message in data["bot_messages"]],
        )

@dataclass
class Session:
    """一段连续会话；当前实现以一小时无活动作为会话边界。

    创建者：DialogueState.start_session，由 DialogueEngine._prepare_session 触发。
    生命周期：创建后接收 Turn；超时后写 closed_at，但仍保留在 sessions 历史列表中。
    修改影响：时间字段变化会影响 Engine 的超时判断和历史持久化格式。
    """
    session_id: str
    started_at: float
    last_activity_at: float
    turns: list[Turn] = field(default_factory=list)
    closed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化时间、关闭状态以及有序 Turn 列表。"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "turns": [turn.to_dict() for turn in self.turns],
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """从 JSON 递归恢复 Session 与内部 Turns。"""
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            last_activity_at=data["last_activity_at"],
            turns=[Turn.from_dict(turn) for turn in data["turns"]],
            closed_at=data["closed_at"],
        )

@dataclass
class DialogueState:
    """以 sender_id 为单位保存的对话、任务和对象状态。

    存在原因：HTTP 无状态，而客服任务需要跨请求记住 Flow Step、Slots 和历史。
    创建者：新用户由 DialogueRepository 创建；老用户由 ``from_dict`` 恢复。
    生命周期：与 sender_id 长期绑定，每轮请求加载、原地修改、整体保存。
    协作：Engine 管理会话/轮次，CommandProcessor 管理任务切换，FlowExecutor 推进步骤，
    Planner/Responder 只读取上下文，Repository 负责持久化。
    修改影响：任何字段变更都要同步 to_dict/from_dict、Prompt 输入和旧数据兼容。
    """

    # 用户唯一标识，也是 dialogue_states 表的主键。
    sender_id: str

    # 当前用户业务；FlowExecutor 会从 step_id 指向的位置继续推进。
    active_task: TaskContext | None = None

    # 被新任务、知识问答或闲聊暂时让出的用户任务。
    paused_tasks: list[TaskContext] = field(default_factory=list)

    # 提示/收集等系统辅助任务；存在时拥有更高执行优先级。
    active_system_task: SystemContext | None = None

    # 最近选中的商品或订单，为“这个/它”提供结构化上下文。
    focused_object: FocusedObject | None = None

    # 历史 Session；每个 Session 内部保存完整 turns。
    sessions: list[Session] = field(default_factory=list)
    current_session_id: str | None = None

    # 当前正在生成回复的一轮，成功结束后才提交进 Session.turns。
    pending_turn: Turn | None = None

    def to_dict(self) -> dict[str, Any]:
        """把完整聚合状态转换为 JSON 兼容字典。

        返回值最终由 DialogueRepository 调用 json.dumps 写入 state_json。
        此函数不修改状态；新增字段时必须在此显式加入，否则下一请求会丢失。
        """
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
        """从数据库字典递归重建完整领域状态。

        输入来自 ``json.loads(DialogueStateRecord.state_json)``；返回对象交给
        DialogueService/Engine。当前直接索引 key，尚未处理旧版本缺字段兼容。
        """
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
        """结束系统辅助任务，让 FlowExecutor 下一次选择 active_task。

        调用者包括 SetSlotsCommand 命中等待槽位、StartFlowCommand 清理旧提示以及
        FlowExecutor 执行系统 EndStep。不会改变底层用户任务进度。
        """
        self.active_system_task = None

    def pause_active_task(self) -> None:
        """保留当前业务进度并移入 paused_tasks。

        原 TaskContext 对象整体移动，因此 flow_id、step_id、slots 都保留；随后清空
        active_task，避免两个用户任务同时推进。Knowledge/Chitchat 分流和任务切换会调用。
        """
        if self.active_task:
            self.paused_tasks.append(self.active_task)
            self.active_task = None

    def start_new_task(self, task:TaskContext)->None:
        """将传入 TaskContext 设为唯一 active_task；本函数不自动暂停旧任务。"""
        self.active_task = task

    def start_new_system_task(self, system_task:SystemContext)->None:
        """设置高优先级系统辅助任务；若已有系统任务会直接覆盖。"""
        self.active_system_task = system_task

    def cancel_active_task(self) -> None:
        """取消当前业务；与 pause 不同，不写入 paused_tasks，因此不能恢复。"""
        self.active_task = None

    def match_task_to_resume(self, flow_id: str) -> TaskContext | None:
        """按 Flow ID 查找可恢复 TaskContext。

        返回原对象或 None，不修改 paused_tasks。CommandProcessor 当前直接重新激活返回值；
        因此恢复后列表仍有重复引用，这是后续需要修复的状态一致性问题。
        """
        for task in self.paused_tasks:
            if task.flow_id == flow_id:
                return task
        return None

    def set_slots(self, slots: dict[str, Any]) -> None:
        """把新槽位或 ActionResult 合并进当前用户任务。

        同名 key 会覆盖旧值；调用者必须保证 active_task 存在。修改后的槽位随后可能被
        CollectStep 判断、Jinja2 回复模板读取，或在保存后供下一轮 Planner 使用。
        """
        self.active_task.slots.update(slots)

    def current_task(self):
        """返回当前应优先执行的上下文；系统任务存在时优先于用户任务。"""
        return self.active_system_task or self.active_task

    def remove_active_task_slots(self, slot_name):
        """删除校验失败的槽位，使 CollectStep 下一次能够重新询问用户。"""
        self.active_task.slots.pop(slot_name)

    def end_user_task(self):
        """用户 Flow 到达 EndStep 后清空 active_task；已完成任务不会进入 paused_tasks。"""
        self.active_task = None

    def current_session(self)->Session | None:
        """根据 current_session_id 在线性列表中找到当前 Session；找不到返回 None。"""
        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session
        return None

    def start_session(self):
        """创建并激活一个新 Session。

        同一时间值用于 started_at/last_activity_at；UUID 避免依赖数据库生成 ID。
        新 Session 追加而非覆盖，历史会话因此仍可用于未来 history 接口。
        """
        now = time.time()
        session = Session(
            session_id=str(uuid.uuid4()),
            started_at=now,
            last_activity_at=now,
        )
        self.sessions.append(session)
        self.current_session_id = session.session_id

    def close_current_session(self):
        """写入 closed_at 并解除 current_session_id；调用者需确保当前 Session 存在。"""
        self.current_session().closed_at = time.time()
        self.current_session_id = None

    def reset_runtime_state_for_new_session(self):
        """清空跨会话不应继承的运行状态，但保留 sessions 历史。

        超过一小时后旧任务、聚焦对象和暂停任务全部失效，避免用户隔天回来意外续办。
        """
        self.active_task = None
        self.active_system_task = None
        self.focused_object = None
        self.paused_tasks = []

    def begin_turn(self, message: Message):
        """为最新消息创建 pending_turn。

        当前消息暂不进入 Session.turns，因此 Planner 可以把“已完成历史”和“本轮输入”
        分开传给模型。若处理失败，Repository 不保存时也不会出现半轮历史。
        """
        self.pending_turn = Turn(
            turn_id=str(uuid.uuid4()),
            user_message=message,
            bot_messages=[],
        )

    def commit_pending_turn(self):
        """将已补齐机器人回复的 pending_turn 提交到当前 Session。

        调用者是 DialogueEngine.process_message；提交后清空 pending_turn，避免下一轮复用。
        """
        self.current_session().turns.append(self.pending_turn)
        self.pending_turn = None

    def set_focused_object(self, param):
        """覆盖当前聚焦对象；新值会参与后续知识校验、Prompt 和 collect 自动补槽。"""
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









