from pathlib import Path

from pydantic_settings.sources.providers import aws

from app.chitchat.handler import ChitchatHandler
from app.chitchat.responder import ChitchatResponder
from app.clarify.clarify_respond import ClarifyResponder
from app.domain.contexts import CollectSystemContext
from app.domain.dialogue_service_domain import Message, ProcessResult, MessageType, BotMessage
from app.domain.dialogue_state import DialogueState, FocusedObject
from app.knowledge.handler import KnowledgeHandler
from app.knowledge.intention import KNOWLEDGE_INTENTS
from app.knowledge.provider import ProductAPIProvider, OrderAPIProvider, FAQProvider, RAGProvider
from app.knowledge.register import KnowledgeProviderRegistry
from app.knowledge.responder import KnowledgeResponder
from app.plan.models import ClarifyReason
from app.plan.planner import TurnPlanner
from app.plan.validator import TurnPlanValidator
from app.task.action.builder import build_action_runner
from app.task.command.models import Command, SetSlotsCommand
from app.task.command.processor import CommandProcessor
from app.task.flow.flow_executor import FlowExecutor
from app.task.flow.loader import FlowLoader
from app.task.flow.models import FlowsList
from app.task.flow.steps import CollectSlotStep
from app.task.handler import TaskHandler
import time

_PROJECT_ROOT = Path(__file__).parents[2]
_FLOW_CONFIG_DIR = _PROJECT_ROOT / "flow_config"
_FLOW_CONFIG_FILES = (
    "user_flows.yml",
    "system_flows.yml",
)


class DialogueEngine:
    def __init__(
            self,
            turn_planner: TurnPlanner,
            task_handler: TaskHandler,
            knowledge_handler: KnowledgeHandler,
            chitchat_handler: ChitchatHandler,
            clarify_responder: ClarifyResponder,
            turn_plan_validator: TurnPlanValidator,
    ) -> None:
        self.turn_planner = turn_planner
        self.task_handler = task_handler
        self.knowledge_handler = knowledge_handler
        self.chitchat_handler = chitchat_handler
        self.clarify_responder = clarify_responder
        self.turn_plan_validator = turn_plan_validator


    async def process_message(
            self,
            state: DialogueState,
            user_message: Message,
    ) -> ProcessResult:
        """处理一条消息，直接修改 state，返回本轮结果。"""
        self._prepare_session(state)
        self._begin_turn(state, user_message)

        if user_message.type is MessageType.TEXT:
            messages = await self._handle_text_message(
                state=state,
            )
        else:
            state.set_focused_object(
                FocusedObject.from_dict(user_message.object.to_dict())
            )
            messages = await self._handle_object_message(
                message=user_message,
                state=state,
            )

        state.pending_turn.bot_messages.extend(messages)
        state.commit_pending_turn()

        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

    def _prepare_session(self, state: DialogueState) -> None:
        session = state.current_session()
        now = time.time()

        if session is None:
            state.start_session()
            return

        if now - session.last_activity_at > 60 * 60:
            state.close_current_session()
            state.reset_runtime_state_for_new_session()
            state.start_session()
        else:
            session.last_activity_at = now

    def _begin_turn(self, state, user_message):
        state.begin_turn(user_message)

    async def _handle_text_message(
            self,
            state: DialogueState,
    ) -> list[BotMessage]:
        turn_plan = await self.turn_planner.predict(
            state,
            self.task_handler.flows,
            self.knowledge_handler.knowledge_intents,
        )

        validation = self.turn_plan_validator.validate(
            turn_plan,
            state=state,
            knowledge_intents=self.knowledge_handler.knowledge_intents,
        )

        if not validation.valid:
            return await self.clarify_responder.respond(state=state,
                                                        reason=validation.reason)

        if turn_plan.task is not None:
            return await self.task_handler.handle(
                commands=turn_plan.task.commands,
                state=state,
            )

        elif turn_plan.knowledge is not None:
            if state.active_task:
                state.pause_active_task()

            return await self.knowledge_handler.handle(
                state=state,
                intents=turn_plan.knowledge.intents,
            )

        if state.active_task:
            state.pause_active_task()

        return await self.chitchat_handler.handle(state=state)


    async def _handle_object_message(
            self,
            message: Message,
            state: DialogueState,
    ) -> list[BotMessage]:
        command = self._object_slot_command(
            message=message,
            state=state,
            flows=self.task_handler.flows,
        )

        if command is None:
            return self.clarify_responder.respond(state=state,
                                                  reason=ClarifyReason.OBJECT_REQUIRES_INTENT)

        return await self.task_handler.handle(
            commands=[command],
            state=state,
        )

    def _object_slot_command(
            self,
            message: Message,
            state: DialogueState,
            flows: FlowsList,
    ) -> Command | None:
        message_object = message.object
        object_type = message_object.type.strip().lower()
        collect_slot_name = self._current_collect_slot_name(
            state=state,
            flows=flows,
        )

        if object_type == "order" and collect_slot_name == "order_number":
            return SetSlotsCommand(
                command="set_slots",
                slots={"order_number": message_object.id},
            )

        if object_type == "product" and collect_slot_name == "product_id":
            return SetSlotsCommand(
                command="set_slots",
                slots={"product_id": message_object.id},
            )

        return None

    @staticmethod
    def _current_collect_slot_name(
            state: DialogueState,
            flows: FlowsList,
    ) -> str | None:
        if isinstance(state.active_system_task, CollectSystemContext):
            return state.active_system_task.slot_name or None

        active_task = state.active_task
        if active_task is None:
            return None

        current_flow = flows.flow_by_id(active_task.flow_id)
        current_step = current_flow.get_step_by_id(active_task.step_id)

        if not isinstance(current_step, CollectSlotStep):
            return None

        return current_step.slot_name



def build_dialogue_engine() -> DialogueEngine:
    flow_paths = [
        _FLOW_CONFIG_DIR / filename
        for filename in _FLOW_CONFIG_FILES
    ]
    flows = FlowLoader().load_many(flow_paths)

    return DialogueEngine(
        turn_planner=TurnPlanner(),
        task_handler=TaskHandler(
            flows=flows,
            command_processor=CommandProcessor(),
            flow_executor=FlowExecutor(),
            action_runner=build_action_runner(),
        ),
        knowledge_handler=KnowledgeHandler(
            knowledge_intents=KNOWLEDGE_INTENTS,
            knowledge_responder=KnowledgeResponder(),
            provider_registry=KnowledgeProviderRegistry(
                [
                    ProductAPIProvider(),
                    OrderAPIProvider(),
                    FAQProvider(),
                    RAGProvider(),
                ]
            ),
        ),
        chitchat_handler=ChitchatHandler(
            responder=ChitchatResponder(),
        ),
        clarify_responder=ClarifyResponder(),
        turn_plan_validator=TurnPlanValidator(),
    )
