from typing import Any

from app.config.config import settings
from app.domain.dialogue_state import DialogueState
import app.infrastructure.http_client as http_client
from app.task.action.base import Action, ActionResult


class ActionLookupOrderStatus(Action):
    name = 'action_lookup_order_status'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        order_number = state.active_task.slots.get("order_number")
        url = f"{settings.commerce_api_base_url}/orders/{order_number}"
        response = await http_client.client.get(url)
        data = response.json()["data"]

        return ActionResult(
            slot_updates={
                "order_status": data.get("status", ""),
                "order_summary": f"金额 {data.get('amount')} 元，下单时间 {data.get('created_at', '')}。{data.get('status_desc', '')}",
            }
        )
