"""将 Planner 产生的 Command 确定性地应用到 DialogueState。

Command 是瞬时的状态变更，不是长时间运行的任务：
- start_flow 创建 active_task；
- set_slots 填写当前任务数据；
- cancel_flow 清除当前任务；
- resume_flow 恢复 paused_tasks 中的任务。

命令完成后，FlowExecutor 才会根据新状态推进具体业务步骤。
"""

from app.domain.contexts import CanceledSystemContext, CollectSystemContext, InterruptedSystemContext, ResumedSystemContext, StartedSystemContext, TaskContext
from app.domain.dialogue_state import DialogueState
from app.task.command.models import Command, StartFlowCommand, SetSlotsCommand, CancelFlowCommand, ResumeFlowCommand
from app.task.flow.models import Flow, FlowsList
from app.task.flow.steps import FlowStep

class CommandProcessor:
    """把有限 Command 按顺序解释成 DialogueState 的确定性变更。

    由 TaskHandler 持有并长期复用，本身无状态。它不会执行业务 Action，也不会
    循环推进 Step；完成命令后，TaskHandler 才调用 FlowExecutor。
    """

    def run(
        self,
        commands: list[Command],
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        """依次应用全部命令。

        参数:
            commands: 顺序具有语义的命令列表；
            state: 被原地修改的当前用户状态；
            flows: 根据 flow id 查名称、起始 step 和系统 Flow 的配置集合。
        返回:
            无；所有结果都体现在 state 上。
        """
        # 命令顺序有业务意义，例如 resume_flow 必须先于 set_slots。
        for command in commands:
            self._apply(command, state, flows)

    def _apply(
        self,
        command: Command,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        """按命令实际类型分派到唯一处理函数。

        这里依赖 ``Command.from_dict`` 已将普通 JSON 变成已知子类。新增命令时若
        只改 mapping_types 而漏改本分支，命令会被静默忽略。
        """
        # isinstance 将统一的 Command 基类分发到具体状态变更逻辑。
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
        """启动目标 Flow；必要时暂停旧任务并插入“任务切换”系统 Flow。

        start_flow 的三种情况：同一任务已经活动则不动；另一任务活动则保存旧
        TaskContext 后切换；没有活动任务则直接从目标 start step 创建任务。
        系统提示任务拥有更高执行优先级，但底下 active_task 已经建立好，提示
        Flow 结束后 Executor 会自然回到它。
        """

        target_flow_id: str = command.flow

        # 从已加载的 YAML Flow 中取得起始 Step。
        # 未知 flow id 会在此失败，避免创建一个无法由 Executor 定位的 TaskContext。
        target_flow: Flow = flows.flow_by_id(target_flow_id)
        start_step: FlowStep = target_flow.start_step()

        # 新命令到来时，旧的提示/收集系统任务不再继续占用调度权。
        state.end_system_task()

        if state.active_task:
            if state.active_task.flow_id == target_flow_id:
                # 重复启动同一任务时保持原 step 和 slots，避免进度被重置。
                return
            else:
                # 启动不同任务：先把旧任务完整移入 paused_tasks。
                active_flow = flows.flow_by_id(state.active_task.flow_id)
                state.pause_active_task()

                # 新 Flow 从其 start Step 开始执行。
                state.start_new_task(TaskContext(
                    flow_id=target_flow_id,
                    step_id=start_step.id
                ))

                # 创建高优先级系统任务，先向用户说明任务切换。
                interrupted_flow = flows.flow_by_id("system_task_interrupted")
                state.start_new_system_task(InterruptedSystemContext(
                    flow_id="system_task_interrupted",
                    step_id=interrupted_flow.start_step().id,
                    started_flow_id=target_flow_id,
                    started_flow_name=target_flow.name,
                    interrupted_flow_id=active_flow.id,
                    interrupted_flow_name=active_flow.name,
                ))

        else:
            # 没有正在办理的业务，直接创建新的 active_task。
            state.start_new_task(TaskContext(
                flow_id=target_flow_id,
                step_id=start_step.id
            ))

            # 用户任务开始前先执行简短的“已开始处理”系统 Flow。
            started_flow = flows.flow_by_id("system_task_started")
            state.start_new_system_task(StartedSystemContext(
                flow_id="system_task_started",
                step_id=started_flow.start_step().id,
                started_flow_id=target_flow_id,
                started_flow_name=target_flow.name,
            ))


    def _handle_set_slots(
        self,
        command: SetSlotsCommand,
        state: DialogueState,
    ) -> None:
        """将槽位合并到原 active_task，并解除已满足的临时收集任务。

        这是“暂停收集后继续原任务”的核心：active_task 从未被替换，Collect 系统
        Flow 只是临时占据 ``active_system_task``。槽位到达后关闭系统任务，原
        TaskContext 的 flow_id/step_id/已有 slots 都还在原处。
        """
        slots = command.slots
        if state.active_task:
            # update 支持一次命令同时填写多个槽位。
            state.active_task.slots.update(slots)

            # CollectSystemContext 表示上一轮正在等待某个具体槽位。
            system_task = state.active_system_task
            if isinstance(system_task, CollectSystemContext) \
                    and system_task.slot_name in slots \
                    and state.active_task.slots.get(system_task.slot_name):
                # 关闭临时收集任务后，FlowExecutor 会重新选择 active_task。
                state.end_system_task()
        else:
            # 没有 active_task 时槽位无处归属，当前实现选择忽略。
            return

    def _handle_cancel_flow(
        self,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        """结束当前用户任务，并启动只负责反馈结果的取消系统 Flow。

        本实现假定 active_task 存在；Planner/调用者若在空状态下发 cancel_flow，
        读取 ``active_task.flow_id`` 会失败。取消不是暂停：TaskContext 不进入
        paused_tasks，之后不能通过 resume_flow 恢复。
        """
        active_task = state.active_task
        cancelled_flow_id = active_task.flow_id
        cancelled_flow = flows.flow_by_id(cancelled_flow_id)

        state.cancel_active_task()

        canceled_system_flow = flows.flow_by_id("system_task_canceled")

        state.start_new_system_task(CanceledSystemContext(
            flow_id="system_task_canceled",
            step_id=canceled_system_flow.start_step().id,
            canceled_flow_id=cancelled_flow.id,
            canceled_flow_name=cancelled_flow.name,
        ))

    def _handle_resume_flow(
        self,
        command: ResumeFlowCommand,
        state: DialogueState,
        flows: FlowsList,
    ) -> None:
        """恢复指定 Flow；若另有活动任务，先暂停当前任务。

        无活动任务时通过 ``match_task_to_resume`` 找回原 TaskContext，因此保存的
        step_id 和 slots 得以保留。当前另有活动任务的分支却从目标 Flow 起点新建
        TaskContext，没有取出 paused_tasks 的旧现场；这是现实现的语义差异，若
        修复需同时决定暂停列表中旧对象是否移除以及重复恢复策略。
        """
        resumed_flow_id = command.flow
        resumed_flow = flows.flow_by_id(resumed_flow_id)
        active_task = state.active_task

        if active_task:
            if active_task.flow_id == resumed_flow_id:
                # 请求恢复的就是当前任务，不需要改变状态。
                return
            else:
                # 当前另有业务：先暂停它，再切换到目标 Flow。
                interrupted_flow = flows.flow_by_id(active_task.flow_id)
                state.pause_active_task()
                state.start_new_task(TaskContext(
                    flow_id=resumed_flow_id,
                    step_id=resumed_flow.start_step().id
                ))
                interrupted_system_flow = flows.flow_by_id("system_task_interrupted")
                state.start_new_system_task(InterruptedSystemContext(
                    flow_id="system_task_interrupted",
                    step_id=interrupted_system_flow.start_step().id,
                    started_flow_id=resumed_flow_id,
                    started_flow_name=resumed_flow.name,
                    interrupted_flow_id=interrupted_flow.id,
                    interrupted_flow_name=interrupted_flow.name,
                ))
        else:
            # 从 paused_tasks 找回原对象，因此原 step_id 和 slots 都能保留。
            # 返回的是暂停列表中的原上下文，而不是根据 Flow 重新创建的空任务。
            task = state.match_task_to_resume(resumed_flow_id)
            state.start_new_task(task)

            # 先提示用户“继续刚才的任务”，然后再回到用户 Flow。
            resumed_system_flow = flows.flow_by_id("system_task_resumed")
            state.start_new_system_task(ResumedSystemContext(
                flow_id="system_task_resumed",
                step_id=resumed_system_flow.start_step().id,
                resumed_flow_id=resumed_flow.id,
                resumed_flow_name=resumed_flow.name,
            ))

