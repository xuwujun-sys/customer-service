from typing import Any
from dataclasses import dataclass, field

from app.domain.dialogue_state import DialogueState
from app.task.action.base import ActionResult
from app.task.action.register import ActionRegistry


@dataclass
class ActionCall:
    action_name: str
    action_kwargs: dict[str, Any] = field(default_factory=dict)


class ActionRunner:
    """Execute actions requested by the flow executor."""

    def __init__(
        self,
        registry: ActionRegistry,
    ) -> None:
        self.registry = registry

    async def run(
        self,
        action_call: ActionCall,
        state: DialogueState,
    ) -> ActionResult:
        action_name = action_call.action_name
        action = self.registry.get(action_name)
        return await action.run(state, action_call.action_kwargs)

action_runner = ActionRunner()
