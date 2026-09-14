from dataclasses import asdict

from app.domain.contexts import CollectSystemContext
from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.task.action.actionrunner import ActionCall
from app.task.flow.models import FlowsList, Flow
from app.task.action.actionrunner import ActionRunner
from app.task.flow.steps import *

class FlowExecutor():

    async def run_task(self, state: DialogueState, flows: FlowsList, action_runner: ActionRunner) -> list[BotMessage]:
        messages = []
        while True:
            action_call = self.advance_until_action(state, flows)
            if action_call.action_name == "action_listen":
                break
            else:
                action_res = await action_runner.run(action_call,state)
                state.set_slots(action_res.slot_updates)
                messages.extend(action_res.messages)
        return messages

    def advance_until_action(self, state: DialogueState, flows: FlowsList) -> ActionCall:

        while True:
            current_task = state.active_system_task or state.active_task
            if current_task is None:
                return ActionCall(action_name="action_listen")

            flow: Flow | None= flows.flow_by_id(current_task.flow_id)
            step: FlowStep | None = flow.step_by_id(current_task.step_id)
            step_res: ActionCall | None = self._run_step(step, state, flows)

            if step_res is not None:
                return step_res

    def _run_step(self, step, state,flows: FlowsList)->ActionCall | None:
        if isinstance(step, StartFlowStep):
            return self._run_start_step(step, state)
        if isinstance(step, CollectSlotStep):
            return self._run_colletc_step(step, state, flows)
        if isinstance(step, ActionFlowStep):
            return self._run_action_step(step, state)
        if isinstance(step, EndFlowStep):
            return self._run_end_step(state)

    def _run_start_step(self, step: StartFlowStep, state: DialogueState)->ActionCall | None:
        self._advance_next_step(step, state)

    def _run_colletc_step(self, step: CollectSlotStep, state: DialogueState,flows: FlowsList)->ActionCall | None:
        self._try_to_fill_slot_from_focused_object(step, state)
        if state.active_task.slots.get(step.slot_name, None):
            pass

            if step.validation:
                if self._eval_cond(step.validation.condition, state):
                    self._advance_next_step(step, state)
                    return None
                else:
                    if step.response:
                        return ActionCall(action_name="action_response",
                                          action_kwargs=asdict(step.validation.failure_response))

                    else:
                        state.remove_active_task_slots(step.slot_name)
                        return None

            else:
                self._advance_next_step(step, state)
                return None

        else:
            state.start_new_system_task(CollectSystemContext(
                flow_id="system_collect_information",
                step_id=flows.flow_by_id("system_collect_information").start_step().id,
                slot_name=step.slot_name,
                response=asdict(step.response)
            ))
            return None

        return None

    def _run_action_step(self, step: ActionFlowStep, state: DialogueState)->ActionCall | None:
        action_call = self._build_action_call(step, state)
        self._advance_next_step(step, state)
        return action_call

    def _run_end_step(self,state: DialogueState)->ActionCall | None:
        if state.active_system_task:
            state.end_system_task()
            return None
        if state.active_task:
            state.end_user_task()
            return None

    def _select_next_step(self,step: FlowStep,state: DialogueState)->str | None:
        links: List[FlowStepLink] = step.next
        for link in links:
            if isinstance(link, StaticLink):
                return link.target

            if isinstance(link, ConditionalLink):
                condition = link.condition
                if self._eval_cond(condition, state):
                    return link.target

            if isinstance(link, FallbackLink):
                return link.target

    def _eval_cond(self, condition: str, state:DialogueState)->bool:
        current_task = state.active_system_task or state.active_task
        data = {
            "context": current_task.to_dict() if current_task else {},
            "slots": state.active_task.slots if state.active_task else {}
        }
        return bool(eval(condition, {"__builtins__": {}}, data))

    def _advance_next_step(self,step: FlowStep,state: DialogueState):

        res = self._select_next_step(step,state)
        # 步进要作用于"当前正在执行"的任务：系统任务在执行时是 active_system_task
        current_task = state.active_system_task or state.active_task
        current_task.step_id = res

    def _build_action_call(self, step: ActionFlowStep, state: DialogueState) -> ActionCall:
        action_name = step.action
        args = step.args
        if isinstance(args, str):
            args = asdict(state.active_system_task or state.active_task)[args.split('.')[1]]
        return ActionCall(action_name=action_name, action_kwargs=args)

    def _try_to_fill_slot_from_focused_object(self, step : CollectSlotStep, state:DialogueState)->None:
        if state.focused_object is None:
            return None
        if step.slot_name == 'order_number' and state.focused_object.type == 'order':
            state.set_slots({step.slot_name: state.focused_object.id})
        if step.slot_name == 'product_id' and state.focused_object.type == 'product':
            state.set_slots({step.slot_name: state.focused_object.id})





