from typing import Any

from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.prompts.build_history import BuildHistory
from app.task.action.base import Action, ActionResult
from jinja2 import Template
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from app.infrastructure.llm import llm

class ActionResponse(Action):
    name = 'action_response'
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        context = state.active_system_task or state.active_task
        text = action_kwargs.get("text", "")
        prompt = action_kwargs.get("prompt", "")
        model = action_kwargs.get("model", "static")

        if model == "static":
            rendered_text = self._render_template(text, state, context)
            return ActionResult(messages=[BotMessage(text=rendered_text)])
            
        elif model == "rephrase":
            rendered_text = self._render_template(text, state, context)
            llm_res = await self._call_llm(state, prompt, rendered_text)
            return ActionResult(messages=[BotMessage(text=llm_res)])
            
        else:
            llm_res = await self._call_llm(state, prompt)
            return ActionResult(messages=[BotMessage(text=llm_res)])

    def _render_template(self, template: str, state: DialogueState, context) -> str:
        jinja_template = Template(template)
        rendered_text = jinja_template.render(
            slots=state.active_system_task.slots if state.active_system_task else {},
            context=context
        )
        return rendered_text

    async def _call_llm(self, state, prompt, rendered_text="") -> str:
        template = PromptTemplate(
            prompt=prompt,
            template_format="jinja2"
        )
        stroutputparser = StrOutputParser()
        chain = template | llm | stroutputparser

        result = await chain.ainvoke(
           { "history" : BuildHistory.build_history(state.turns),
            "user_message" : BuildHistory.get_latest_user_message(state.pending_turn),
            "current_response" : rendered_text,}
        )

        return result

        