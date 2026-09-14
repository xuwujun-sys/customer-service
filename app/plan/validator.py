from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan, TurnPlanValidationResult, ClarifyReason


class TurnPlanValidator:
    def validate(
        self,
        turn_plan: TurnPlan,
        state: DialogueState,
        knowledge_intents: dict[str, KnowledgeIntent],
    ) -> TurnPlanValidationResult:
        active_tracks = self._active_tracks(turn_plan)

        if not active_tracks:
            return self._reject(ClarifyReason.MISSING_TRACK)

        if len(active_tracks) > 1:
            return self._reject(ClarifyReason.MULTIPLE_TRACKS)

        track = active_tracks[0]

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
        knowledge_plan = turn_plan.knowledge

        if knowledge_plan is None or not knowledge_plan.intents:
            return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

        focused_object = state.focused_object

        for intent in knowledge_plan.intents:
            intent_meta = knowledge_intents[intent]
            required_object = intent_meta.requires_object

            if required_object is not None:
                if focused_object is None or focused_object.type != required_object:
                    return self._reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        return TurnPlanValidationResult(valid=True)

    def _reject(
            self,
            reason: ClarifyReason,
    ) -> TurnPlanValidationResult:
        return TurnPlanValidationResult(
            valid=False,
            reason=reason,
        )