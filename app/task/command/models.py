"""Planner 与任务执行层之间的受限 Command 协议。

LLM 不能直接调用 Python 方法或写 DialogueState，只能输出本文件白名单中的四种
声明式命令。``TurnPlan.from_dict`` 将 JSON 转成具体 dataclass，TaskHandler 再
交给 CommandProcessor 执行。这形成“非确定性理解 -> 有限协议 -> 确定性修改”。

修改命令字段时，必须同步更新 plan Prompt 示例、``mapping_types``、Processor
分派逻辑和可能消费字段的 Flow 状态代码。
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Command:
    """所有任务命令的共同基类，仅保存用于反序列化分派的命令名。"""
    command: str

    @staticmethod
    def from_dict(data: Dict[str, Any]):
        """依据 JSON 的 ``command`` 字段构造具体命令子类。

        未注册名称会在 ``mapping_types`` 查找处抛 KeyError，这是阻止任意命令
        进入 Processor 的白名单边界。当前异常发生在 Validator 之前。
        """
        # 根据 LLM 返回的 command 字段选择具体 dataclass。
        cls = mapping_types[data["command"]]
        return cls(**data)

@dataclass
class StartFlowCommand(Command):
    """要求启动 ``flow`` 指定的新业务 Flow；flow 值必须匹配 YAML 的 id。"""
    flow: str

@dataclass
class SetSlotsCommand(Command):
    """把结构化 ``slots`` 合并进当前 active_task，不会创建新的 Task。"""
    slots: dict[str, Any]


@dataclass
class CancelFlowCommand(Command):
    """取消当前 active_task；取消后的提示由系统 Flow 负责。"""
    pass


@dataclass
class ResumeFlowCommand(Command):
    """按 Flow ID 恢复任务；目标应与 ``paused_tasks`` 中的现场对应。"""
    flow: str

# 白名单映射既是 JSON 反序列化表，也是 LLM 可操作状态的安全边界。
mapping_types = {
    "start_flow": StartFlowCommand,
    "set_slots": SetSlotsCommand,
    "cancel_flow": CancelFlowCommand,
    "resume_flow": ResumeFlowCommand,
}
