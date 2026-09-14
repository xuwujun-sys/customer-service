from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.task.action.actionrunner import ActionRunner
from app.task.command.models import Command
from app.task.command.processor import CommandProcessor
from app.task.flow.flow_executor import FlowExecutor
from app.task.flow.models import FlowsList


class TaskHandler:
    def __init__(self,
                 command_processor: CommandProcessor,
                 flows: FlowsList,
                 flow_executor: FlowExecutor,
                 action_runner: ActionRunner
                 ):
        self.command_processor: CommandProcessor = command_processor
        self.flows: FlowsList = flows
        self.flow_executor: FlowExecutor = flow_executor
        self.action_runner: ActionRunner = action_runner

    async def handle(self, commands: list[Command], state: DialogueState) -> list[BotMessage]:
        #command_processor.run相当于是跟新DialogueState
        self.command_processor.run(commands, state, self.flows)
        #flow_executor.run_task再根据跟新的DialogueState具体实现工作流
        messages: list[BotMessage] = await self.flow_executor.run_task(state, self.flows, self.action_runner)
        return messages
