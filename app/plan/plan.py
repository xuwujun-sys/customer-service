import json
from dataclasses import asdict
from typing import Any
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan
from app.prompts.load_prompt import load_prompt
from app.prompts.build_history import BuildHistory
from app.domain.dialogue_service_domain import MessageType
from app.task.flow.models import FlowsList


def get_user_message(self, user_message):
    if user_message.type == MessageType.TEXT:
        return user_message.text
    elif user_message.type == MessageType.OBJECT:
        return str(user_message.object.to_dict())

def _build_prompt_inputs(
    self,
    state: DialogueState,
    flows: FlowsList,
    knowledge_intents: dict[str, KnowledgeIntent],
) -> dict[str, Any]:
    """把当前对话状态整理成 turn_plan 提示词需要的输入变量。"""

    user_message = self.get_user_message(
        state.pending_turn.user_message
    )

    history = BuildHistory.build_history(
        state.current_session().turns
    )

    available_flows = [
        {
            key: value
            for key, value in asdict(flow).items()
            if key != "steps"
        }
        for flow in flows.flows
    ]

    knowledge_intent_list = [
        {
            "id": intent.id,
            "description": intent.description,
        }
        for intent in knowledge_intents.values()
    ]

    return {
        "current_conversation": history,
        "user_message": user_message,

        "available_flows_json": json.dumps(
            {"flows": available_flows},
            ensure_ascii=False,
        ),

        "active_task_json": json.dumps(
            asdict(state.active_task)
            if state.active_task is not None
            else None,
            ensure_ascii=False,
        ),

        "interrupted_tasks_json": json.dumps(
            [
                asdict(task)
                for task in state.paused_tasks
            ],
            ensure_ascii=False,
        ),

        "focused_object_json": json.dumps(
            asdict(state.focused_object)
            if state.focused_object is not None
            else None,
            ensure_ascii=False,
        ),

        "knowledge_intents_json": json.dumps(
            knowledge_intent_list,
            ensure_ascii=False,
        ),
    }


async def _predict_from_prompt_inputs(
    self,
    prompt_inputs: dict[str, Any],
) -> TurnPlan:
    """调用 LLM，根据提示词输入生成本轮 TurnPlan。"""

    prompt_text = load_prompt("plan_prompt")

    prompt = PromptTemplate.from_template(
        prompt_text,
        template_format="jinja2",
    )

    from app.infrastructure.llm import llm
    chain = (
        prompt
        | llm
        | JsonOutputParser()
    )

    llm_output: dict = await chain.ainvoke(prompt_inputs)

    return TurnPlan.from_dict(llm_output)