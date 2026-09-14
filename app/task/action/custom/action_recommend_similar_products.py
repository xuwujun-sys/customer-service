from typing import Any

from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.task.action.base import Action, ActionResult


class ActionRecommendSimilarProducts(Action):
    name = 'action_recommend_similar_products'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        # 推荐能力后续接入，先给出兜底回复，避免流程中断
        return ActionResult(
            messages=[BotMessage(text="相似商品推荐能力还在建设中，你可以先告诉我更具体的需求，我帮你参考。")]
        )
