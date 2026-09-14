
from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan
from app.task.flow.models import FlowsList
from app.plan.plan import _predict_from_prompt_inputs, _build_prompt_inputs


class TurnPlanner:
    async def predict(
            self,
            state: DialogueState,
            flows: FlowsList,
            knowledge_intents: dict[str, KnowledgeIntent],
    ) -> TurnPlan:
        prompt_inputs = _build_prompt_inputs(state, flows, knowledge_intents)
        return await _predict_from_prompt_inputs(prompt_inputs)

