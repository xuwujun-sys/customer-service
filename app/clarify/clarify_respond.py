"""澄清回复模块：把不可执行计划转换为自然、具体的追问。

上游是 DialogueEngine 和 TurnPlanValidator；下游是 Prompt/LLM。Validator 负责
给出稳定的 ``ClarifyReason``，本模块先映射成可靠的基础话术，再让 LLM 结合
历史与聚焦对象润色。它不修改任务或槽位，只返回 BotMessage。

新增 ClarifyReason 时，必须同步扩展 ``build_clarify_message``，否则会落入通用
兜底文案。Prompt 变量名也必须与 ``clarify_respond.jinja2`` 保持一致。
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_service_domain import BotMessage, MessageType
from app.domain.dialogue_state import DialogueState
from app.plan.models import ClarifyReason
from app.prompts.load_prompt import load_prompt
from app.prompts.build_history import BuildHistory
import json

class ClarifyResponder:
    """为信息不足、轨道冲突或对象用途不明生成澄清问题。

    由 ``build_dialogue_engine`` 创建并长期复用；实例不保存用户状态。每次调用
    都从传入 DialogueState 读取当前消息、历史和 focused_object。
    """

    async def respond(
        self,
        state: DialogueState,
        reason: ClarifyReason,
    ) -> list[BotMessage]:
        """生成一条结合上下文润色后的澄清回复。

        参数:
            state: 当前对话状态，pending_turn 是本轮用户输入；
            reason: Validator 或对象消息分支给出的标准失败原因。
        返回:
            只含一条文本 BotMessage 的列表，以符合各 Handler 统一返回协议。

        执行流程:
            原因码 -> 基础澄清话术 -> 整理当前消息/历史/对象 -> 渲染 Prompt
            -> LLM 润色 -> BotMessage。
        状态影响:
            只读，不会取消或推进任务；本轮历史由 Engine 统一提交。
        """
        # pending_turn 在 Engine._begin_turn 中创建，因此这里读到的就是本轮输入。
        message = state.pending_turn.user_message

        # 先用确定性代码生成语义正确的话术，避免完全依赖模型自由发挥。
        clarify_message = self.build_clarify_message(
            reason=reason,
            state=state,
        )

        user_message = self.get_user_message(message)
        history = BuildHistory.build_history(state.current_session().turns)
        # 聚焦对象帮助模型把“请发送对象”说成“这个订单/这个商品”的自然表达。
        focused_object = json.dumps(state.focused_object.to_dict()) if state.focused_object else None

        prompt_text = load_prompt("clarify_respond")
        prompt = PromptTemplate.from_template(
            prompt_text,
            template_format="jinja2",
        )

        from app.infrastructure.llm import llm
        chain = prompt | llm | StrOutputParser()

        # LLM 只负责改写表达，不负责重新规划轨道或执行任何命令。
        rewritten = await chain.ainvoke(
            {
                "reason": reason.value,
                "clarify_message": clarify_message,
                "focused_object": focused_object,
                "history": history,
                "user_message": user_message,
            }
        )

        return [BotMessage(text=rewritten)]

    def build_clarify_message(
        self,
        reason: ClarifyReason,
        state: DialogueState,
    ) -> str:
        """把标准澄清原因映射为含义明确的基础中文话术。

        参数:
            reason: 规划校验失败或对象用途不明确的原因；
            state: OBJECT_REQUIRES_INTENT 分支需要读取 focused_object 类型。
        返回:
            可直接发送、同时也可交给 LLM 润色的基础字符串。
        """
        if reason is ClarifyReason.MULTIPLE_TRACKS:
            return "你这次同时提到了多个方向。我们先处理一个，你想先办业务还是先咨询信息呢？"

        if reason is ClarifyReason.MISSING_FOCUSED_OBJECT:
            return "请先发送你想咨询的商品或订单，我再继续帮你看。"

        if reason is ClarifyReason.MISSING_KNOWLEDGE_INTENT:
            return "你是想了解商品信息、订单信息，还是售后配送规则呢？"

        if reason is ClarifyReason.MISSING_TRACK:
            return "你是想先处理业务问题，还是先咨询信息呢？"

        if reason is ClarifyReason.MISSING_TASK_COMMANDS:
            return "你这次是想办理什么业务呢？比如查订单、查物流，或者申请退款。"

        if reason is ClarifyReason.OBJECT_REQUIRES_INTENT:
            focused_object = state.focused_object

            if focused_object is not None and focused_object.type == "order":
                return "我已经收到这个订单了。你想查订单状态、查物流，还是申请退款呢？"

            if focused_object is not None and focused_object.type == "product":
                return "我已经收到这个商品了。你想了解它的商品信息、发货情况，还是售后相关问题呢？"

        return "我还需要再确认一下你的意思，你可以换个更具体的说法告诉我。"

    def get_user_message(self, user_message):
        """把文本/对象领域消息转为 Prompt 可展示的字符串，不修改消息。"""
        if user_message.type == MessageType.TEXT:
            return user_message.text
        elif user_message.type == MessageType.OBJECT:
            return str(user_message.object.to_dict())
