from typing import Any

from app.config.config import settings
from app.domain.dialogue_state import DialogueState
import app.infrastructure.http_client as http_client
from app.task.action.base import Action, ActionResult


class ActionLookupLogistics(Action):
    name = 'action_lookup_logistics'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        order_number = state.active_task.slots.get("order_number")
        url = f"{settings.commerce_api_base_url}/orders/{order_number}/logistics"
        response = await http_client.client.get(url)
        data = response.json().get("data", {})

        return ActionResult(
            slot_updates={
                "tracking_number": data.get("tracking_number", ""),
                "logistics_company": data.get("logistics_company", ""),
                "logistics_status": f"{data.get('status', '')}，{data.get('status_desc', '')}".rstrip("。"),
            }
        )
