"""Task 业务轨道门面：连接“LLM 计划”与“确定性工作流执行”。

上游 ``DialogueEngine`` 传入已经通过 Validator 的 Command 列表；本模块先交给
``CommandProcessor`` 修改 DialogueState，再让 ``FlowExecutor`` 根据修改后的
flow_id、step_id、slots 继续执行 YAML Flow，最后把回复统一返回给 Engine。

这里的顺序是项目暂停/恢复机制的关键：Command 不是另开一条长期流程，而只是
修改原任务现场；FlowExecutor 随后读取同一个 state，所以可以从保存的 step_id
继续。交换两者顺序会使本轮命令来不及影响工作流。
"""

from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.task.action.actionrunner import ActionRunner
from app.task.command.models import Command
from app.task.command.processor import CommandProcessor
from app.task.flow.flow_executor import FlowExecutor
from app.task.flow.models import FlowsList


class TaskHandler:
    """协调 CommandProcessor、FlowExecutor 与 ActionRunner。

    由 ``build_dialogue_engine`` 创建并注入所有依赖，生命周期与 Engine 一致。
    本类不保存某个用户状态；每次 handle 都只操作参数中的 DialogueState。
    """
    def __init__(self,
                 command_processor: CommandProcessor,
                 flows: FlowsList,
                 flow_executor: FlowExecutor,
                 action_runner: ActionRunner
                 ):
        """保存任务轨道需要的四个共享组件。

        ``flows`` 是启动时解析好的只读配置；processor 改状态；executor 解释流程；
        action_runner 根据动作名找到真正的业务 Action。
        """
        self.command_processor: CommandProcessor = command_processor
        self.flows: FlowsList = flows
        self.flow_executor: FlowExecutor = flow_executor
        self.action_runner: ActionRunner = action_runner

    async def handle(self, commands: list[Command], state: DialogueState) -> list[BotMessage]:
        """应用本轮命令并把变化后的任务运行到下一个等待点。

        参数:
            commands: Planner 生成且已通过 Validator 的有序命令；
            state: 当前用户状态，将被命令处理器和流程执行器原地修改。
        返回:
            Flow 运行期间所有 Action 产生的 BotMessage。

        一次典型补槽调用:
            SetSlotsCommand 写入 active_task.slots -> 收集系统任务结束 -> Executor
            再次选中未丢失的 active_task -> 从原 step_id 检查到槽位已存在 -> 后移。
        """
        # Command 只描述状态要如何变化，例如启动流程或填入订单号。
        self.command_processor.run(commands, state, self.flows)

        # FlowExecutor 读取更新后的 flow_id/step_id/slots，持续推进到 listen 或结束。
        messages: list[BotMessage] = await self.flow_executor.run_task(state, self.flows, self.action_runner)
        return messages
