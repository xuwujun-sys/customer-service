"""Chitchat 轨道入口：从 DialogueState 提取当前消息和历史并委托回复器。

Engine 在调用本模块前会暂停 active_task，所以闲聊不会误填业务槽位。本 Handler
只做状态取数与参数装配，具体 Prompt/LLM 调用由 ChitchatResponder 负责。
"""

import asyncio

from app.chitchat.responder import ChitchatResponder
from app.domain.dialogue_service_domain import BotMessage, Message, MessageType
from app.domain.dialogue_state import DialogueState, Turn


class ChitchatHandler:
    """保持 Engine 与具体 LLM 闲聊实现之间的职责隔离。

    由装配根创建，生命周期与 Engine 相同；只持有无状态 Responder。
    """
    def __init__(
            self,
            responder: ChitchatResponder
    ) -> None:
        """注入负责实际生成文本的闲聊回复器。"""
        self.responder = responder

    async def handle(self, state: DialogueState) -> list[BotMessage]:
        """取出本轮用户消息与此前历史并生成闲聊回复。

        本函数只读 state；回复稍后由 Engine 写入 pending_turn 并统一提交。
        """
        # 当前输入仍在 pending_turn；recent_turns 只包含此前已完成轮次。
        pending_turn = state.pending_turn
        user_message = pending_turn.user_message
        recent_turns = state.current_session().turns
        return await self.responder.respond(
            user_message=user_message,
            recent_turns=recent_turns,
        )



