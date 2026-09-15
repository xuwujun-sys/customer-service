"""内置回复动作：支持静态模板、LLM 改写和完全由 LLM 生成三种模式。"""

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
    """把 YAML 回复定义渲染为标准 BotMessage。

    该内置 Action 被所有系统/用户 Flow 复用。实例由 Builder 注册一次，无用户态。
    ``name`` 必须与 YAML 中大量 ``action: action_response`` 保持一致。
    """

    name = 'action_response'
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """按 static/rephrase/generate 三类模式生成回复。

        参数:
            state: 提供 slots、当前 context、历史和本轮用户消息；
            action_kwargs: 通常由 ResponseDefinition 转成，包含 mode/text/prompt。
        返回:
            只含一条 BotMessage 的 ActionResult，不更新槽位。
        """
        # 系统任务存在时，其 context 优先用于 started/resumed/collect 等模板。
        context = state.active_system_task or state.active_task
        text = action_kwargs.get("text", "")
        prompt = action_kwargs.get("prompt", "")
        # 变量名 model 实际表示“回复模式”，不是 LLM 模型实例。
        model = action_kwargs.get("mode", "static")

        if model == "static":
            # 确定性 Jinja2 渲染，不调用 LLM。
            rendered_text = self._render_template(text, state, context)
            return ActionResult(messages=[BotMessage(text=rendered_text)])
            
        elif model == "rephrase":
            # 先形成可靠底稿，再让 LLM 只负责润色表达。
            rendered_text = self._render_template(text, state, context)
            llm_res = await self._call_llm(state, prompt, rendered_text)
            return ActionResult(messages=[BotMessage(text=llm_res)])
            
        else:
            # 其他模式直接根据 Prompt 生成回复。
            llm_res = await self._call_llm(state, prompt)
            return ActionResult(messages=[BotMessage(text=llm_res)])

    def _render_template(self, template: str, state: DialogueState, context) -> str:
        """用 Jinja2 将当前业务 slots/context 插入静态话术。

        系统任务执行时 context 指系统上下文，但 slots 仍取底层 active_task，因而
        “请提供订单号”和“已切换到某任务”等模板可以分别使用所需数据。
        """
        jinja_template = Template(template)
        rendered_text = jinja_template.render(
            slots=state.active_task.slots if state.active_task else {},
            context=context
        )
        return rendered_text

    async def _call_llm(self, state, prompt, rendered_text="") -> str:
        """携带已完成历史、本轮输入和可选底稿调用 LLM。

        rephrase 模式通过 current_response 提供可靠语义底稿；generate 模式底稿
        为空。Prompt 占位符需与传入字典的三个键保持一致。
        """
        template = PromptTemplate(
            prompt=prompt,
            template_format="jinja2"
        )
        stroutputparser = StrOutputParser()
        chain = template | llm | stroutputparser

        result = await chain.ainvoke(
           { "history" : BuildHistory.build_history(state.current_session().turns),
            "user_message" : BuildHistory.get_latest_user_message(state.pending_turn),
            "current_response" : rendered_text,}
        )

        return result

