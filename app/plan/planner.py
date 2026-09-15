
"""本轮规划器门面：把领域状态转换成 LLM 可执行的结构化规划请求。

DialogueEngine 只调用 ``TurnPlanner.predict``，而 Prompt 拼装、模型调用、JSON
解析细节被委托给 ``plan.py``。这一层让 Engine 不依赖 LangChain，也便于测试时
用假的 Planner 替换模型结果。
"""

from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan
from app.task.flow.models import FlowsList
from app.plan.plan import _predict_from_prompt_inputs, _build_prompt_inputs


class TurnPlanner:
    """把当前对话现场转换为 Task/Knowledge/Chitchat 的结构化计划。

    创建者是 ``build_dialogue_engine``，生命周期与 Engine 相同。它本身无状态，
    每次 predict 都从传入的 DialogueState、Flow 清单、KnowledgeIntent 清单构造
    完整上下文。
    """

    async def predict(
            self,
            state: DialogueState,
            flows: FlowsList,
            knowledge_intents: dict[str, KnowledgeIntent],
    ) -> TurnPlan:
        """预测当前文本消息应走的轨道以及需要执行的动作。

        参数:
            state: 包含已完成历史、本轮 pending_turn、活动/暂停任务和聚焦对象；
            flows: 系统允许 LLM 选择的业务能力清单；
            knowledge_intents: 系统允许 LLM 选择的知识意图字典。
        返回:
            已从 JSON 转成领域对象的 ``TurnPlan``。

        本函数不修改 state。真正状态变化只能发生在 Validator 通过以后，由
        Handler/CommandProcessor 执行计划时产生。
        """
        # 第一步：把领域状态整理成模板需要的普通字符串/JSON 数据。
        prompt_inputs = _build_prompt_inputs(state, flows, knowledge_intents)

        # 第二步：渲染 Prompt、调用 LLM、解析 JSON 并构造 TurnPlan。
        return await _predict_from_prompt_inputs(prompt_inputs)

