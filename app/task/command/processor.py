from app.domain.contexts import CanceledSystemContext, InterruptedSystemContext, ResumedSystemContext, StartedSystemContext, TaskContext
from app.domain.dialogue_state import DialogueState
from app.task.command.models import Command, StartFlowCommand, SetSlotsCommand, CancelFlowCommand, ResumeFlowCommand
from app.task.flow.models import Flow, FlowsList
from app.task.flow.steps import FlowStep

class CommandProcessor:
    def run(
        self,
        commands: list[Command],
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        for command in commands:
            self._apply(command, state, flows)

    def _apply(
        self,
        command: Command,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        if isinstance(command, StartFlowCommand):
            self._handle_start_flow(command, state, flows)
        elif isinstance(command, SetSlotsCommand):
            self._handle_set_slots(command, state)
        elif isinstance(command, CancelFlowCommand):
            self._handle_cancel_flow(state, flows)
        elif isinstance(command, ResumeFlowCommand):
            self._handle_resume_flow(command, state, flows)

    def _handle_start_flow(
        self,
        command: StartFlowCommand,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        
        target_flow_id: str = command.flow
        target_flow: Flow = flows.flow_by_id(target_flow_id)
        start_step: FlowStep = target_flow.start_step()

        state.end_system_task()

        if state.active_task:
            if state.active_task.flow_id == target_flow_id:
                # 如果当前任务就是要启动的任务，则不做任何操作
                return
            else:
                active_flow = flows.flow_by_id(state.active_task.flow_id)
                state.pause_active_task()
                state.start_new_task(TaskContext(
                    flow_id=target_flow_id,
                    step_id=start_step.id
                ))

                state.start_new_system_task(InterruptedSystemContext(
                    started_flow_id="system_task_interrupted",
                    started_flow_name=flows.flow_by_id("system_task_interrupted").name,
                    interrupted_flow_id=active_flow.id,
                    interrupted_flow_name=active_flow.name,
                    flow_id=target_flow_id,
                    flow_name=target_flow.name,
                ))

        else:
            state.start_new_task(TaskContext(
                flow_id=target_flow_id,
                step_id=start_step.id
            ))

            state.start_new_system_task(StartedSystemContext(
                flow_id=target_flow_id,
                flow_name=target_flow.name,
                started_flow_id="system_task_started",
                started_flow_name=flows.flow_by_id(target_flow_id).name
            ))


    def _handle_set_slots(
        self,
        command: SetSlotsCommand,
        state: DialogueState,
    ) -> None:
        slots = command.slots
        if state.active_task:
            state.active_task.slots.update(slots)
        else:
            return

    def _handle_cancel_flow(
        self,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        active_task = state.active_task
        cancelled_flow_id = active_task.flow_id
        cancelled_flow = flows.flow_by_id(cancelled_flow_id)

        state.cancel_active_task()

        start_step=cancelled_flow.start_step()

        state.start_new_system_task(CanceledSystemContext(
            canceled_flow_id=cancelled_flow.id,
            canceled_flow_name=cancelled_flow.name,
            flow_id="system_task_canceled",
            flow_name=state.flows.flow_by_id(cancelled_flow_id).name,
        ))

    def _handle_resume_flow(
        self,
        command: ResumeFlowCommand,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        resumed_flow_id = command.flow
        resumed_flow = flows.flow_by_id(resumed_flow_id)
        active_task = state.active_task

        if active_task:
            if active_task.flow_id == resumed_flow_id:
                # 如果当前任务就是要恢复的任务，则不做任何操作
                return
            else:
                state.pause_active_task()
                state.start_new_task(TaskContext(
                    flow_id=resumed_flow_id,
                    step_id=resumed_flow.start_step().id
                ))
                state.start_new_system_task(InterruptedSystemContext(
                    started_flow_id="system_task_interrupted",
                    started_flow_name=flows.flow_by_id("system_task_interrupted").name,
                    interrupted_flow_id=active_task.id,
                    interrupted_flow_name=active_task.flow_name,
                    flow_id=resumed_flow_id,
                    flow_name=resumed_flow.name,
                ))
        else:
            task = state.match_task_to_resume(resumed_flow_id)
            state.start_new_task(task)
            state.start_new_system_task(ResumedSystemContext(
                resumed_flow_id=resumed_flow.id,
                resumed_flow_name=resumed_flow.name,
                flow_id="system_task_resumed",
                flow_name=flows.flow_by_id(resumed_flow_id).name,
            ))

        