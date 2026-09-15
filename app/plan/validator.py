"""TurnPlan 的确定性业务校验。

LLM 能输出合法 JSON，并不等于其计划可执行。本模块在进入 Handler 前检查：
是否命中且只命中一条轨道、Task 是否有命令、Knowledge 是否有意图，
以及需要商品/订单的知识意图是否具备正确 focused_object。
"""

from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan, TurnPlanValidationResult, ClarifyReason


class TurnPlanValidator:
    """在任何 Handler 执行前，对 LLM 计划施加确定性业务约束。

    为什么不可缺少:
        JSON 可解析只证明语法正确，不证明业务正确。模型可能不选轨道、同时选
        多轨、漏命令，或在没有商品对象时要求查询商品。Validator 把这些情况
        拦截为正常的澄清分支，阻止不完整计划修改 DialogueState。

    创建者是装配根，实例无状态，可跨请求复用。它只读 TurnPlan 和 State，不
    直接修改任何状态。
    """

    def validate(
        self,
        turn_plan: TurnPlan,
        state: DialogueState,
        knowledge_intents: dict[str, KnowledgeIntent],
    ) -> TurnPlanValidationResult:
        """按“轨道唯一性 -> 轨道内部前置条件”的顺序校验计划。

        参数:
            turn_plan: LLM 结构化输出；
            state: 用于验证聚焦对象等运行上下文；
            knowledge_intents: 已注册意图及其对象依赖。
        返回:
            可执行时 ``valid=True``；否则带标准 ``ClarifyReason``。
        """
        # 先统计 task/knowledge/chitchat 中哪些字段不是 None。
        active_tracks = self._active_tracks(turn_plan)

        # 没选轨道说明模型没有判断出用户想做什么。
        if not active_tracks:
            return self._reject(ClarifyReason.MISSING_TRACK)

        # 引擎一轮只处理一条主轨道，多意图交给用户决定优先级。
        if len(active_tracks) > 1:
            return self._reject(ClarifyReason.MULTIPLE_TRACKS)

        track = active_tracks[0]

        # 不同轨道有各自的前置条件；闲聊无需额外字段，直接通过。
        if track == "task":
            return self._validate_task(turn_plan)

        if track == "knowledge":
            return self._validate_knowledge(
                turn_plan,
                state=state,
                knowledge_intents=knowledge_intents,
            )

        return TurnPlanValidationResult(valid=True)

    @staticmethod
    def _active_tracks(turn_plan: TurnPlan) -> list[str]:
        """按固定顺序收集所有非 None 轨道，用于检查零选或多选。"""
        tracks: list[str] = []

        if turn_plan.task is not None:
            tracks.append("task")

        if turn_plan.knowledge is not None:
            tracks.append("knowledge")

        if turn_plan.chitchat is not None:
            tracks.append("chitchat")

        return tracks

    def _validate_task(
            self,
            turn_plan: TurnPlan,
    ) -> TurnPlanValidationResult:
        """验证 Task 计划确实携带至少一条可供 Handler 执行的 Command。

        Command 的具体合法性主要已在 ``Command.from_dict`` 类型分派时决定；
        此处只检查任务轨道不是一个空壳。
        """
        task_plan = turn_plan.task

        if task_plan is None or not task_plan.commands:
            return self._reject(ClarifyReason.MISSING_TASK_COMMANDS)

        return TurnPlanValidationResult(valid=True)

    def _validate_knowledge(
            self,
            turn_plan: TurnPlan,
            state: DialogueState,
            knowledge_intents: dict[str, KnowledgeIntent],
    ) -> TurnPlanValidationResult:
        """验证知识计划非空，并具备各意图要求的 focused_object。

        Provider 查询商品/订单时需要确定 ID。这里先检查对象类型，避免下游收到
        无法检索的调用。当前直接以 ``knowledge_intents[intent]`` 取值，因此模型
        若输出未注册 ID 会触发 KeyError；未来可在此显式转成校验失败。
        """
        knowledge_plan = turn_plan.knowledge

        if knowledge_plan is None or not knowledge_plan.intents:
            return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

        focused_object = state.focused_object

        for intent in knowledge_plan.intents:
            # 意图元数据声明它是否依赖 product/order 对象。
            intent_meta = knowledge_intents[intent]
            required_object = intent_meta.requires_object

            if required_object is not None:
                # 例如 product_info 没有 product ID 时，Provider 无法可靠检索。
                if focused_object is None or focused_object.type != required_object:
                    return self._reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        return TurnPlanValidationResult(valid=True)

    def _reject(
            self,
            reason: ClarifyReason,
    ) -> TurnPlanValidationResult:
        """统一构造失败结果，不抛异常，让 Engine 路由到澄清对话。"""
        return TurnPlanValidationResult(
            valid=False,
            reason=reason,
        )
