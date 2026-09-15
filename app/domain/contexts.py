"""任务运行上下文。

TaskContext 保存用户业务 Flow 的执行位置和槽位；SystemContext 及其子类
保存系统为了提示、收集、打断/恢复业务而临时执行的辅助 Flow。
"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class TaskContext:
    """一个可跨 HTTP 请求恢复的用户业务任务快照。

    创建者：CommandProcessor 在 start_flow 时创建，或 DialogueState.from_dict 恢复。
    生命周期：从 Flow 启动到 EndStep；被打断时同一对象进入 paused_tasks。
    协作：FlowExecutor 读取/推进 step_id，Command/Action 写入 slots，Planner 将其放入
    Prompt 帮助 LLM 判断用户短句是在补哪个槽位。
    修改影响：字段变化必须同步 DialogueState 序列化、plan.py 和 FlowExecutor。
    """

    # YAML 中的业务 Flow ID，例如 logistics_tracking。
    flow_id: str

    # Flow 当前停留的 Step ID，相当于状态机游标。
    step_id: str | None = None

    # 已收集或由 Action 写回的业务数据，例如 order_number。
    slots: dict = field(default_factory=dict)

    def to_dict(self)->dict[str, Any]:
        """序列化任务游标和已收集槽位，供 DialogueState 保存。"""
        return {
            'flow_id': self.flow_id,
            'step_id': self.step_id,
            'slots': self.slots
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any])->"TaskContext":
        """从数据库状态恢复任务；原 step_id/slots 使流程能跨请求续跑。"""
        return cls(**data)

@dataclass
class SystemContext:
    """系统辅助 Flow 的基础上下文，执行时优先于 TaskContext。

    创建者：CommandProcessor 或 FlowExecutor。
    生命周期：通常只跨一个提示/收集阶段；到 EndStep 后被清空。
    协作：``active_system_task or active_task`` 是 FlowExecutor 的调度优先级规则。
    子类字段同时作为 system_flows.yml 中 ``context.xxx`` 的模板变量。
    """

    # 系统 Flow 自己的 ID，例如 system_collect_information。
    flow_id: str
    step_id: str | None = None

    def to_dict(self)->dict[str, Any]:
        """连同子类字段一起序列化；asdict 会递归处理 dataclass。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any])->"SystemContext":
        """根据 flow_id 选择具体系统上下文子类。

        ``mapping_types`` 的 key 必须与 system_flows.yml 和 CommandProcessor 创建时使用的
        flow_id 一致；否则数据库恢复会在此处失败。
        """
        # 根据 flow_id 恢复具体子类，否则子类特有字段会在反序列化时丢失。
        clz = mapping_types[data["flow_id"]]
        return clz(**data)

@dataclass
class StartedSystemContext(SystemContext):
    """记录刚刚启动的用户 Flow，供 ``system_task_started`` 话术渲染。

    ``started_flow_name`` 对应 YAML 中 ``context.started_flow_name``，修改字段名必须同步。
    """
    started_flow_id: str = ""
    started_flow_name: str = ""


@dataclass
class InterruptedSystemContext(SystemContext):
    """记录被打断任务与新任务，供 system_task_interrupted 连续生成两条说明。"""
    interrupted_flow_id: str = ""
    interrupted_flow_name: str = ""
    started_flow_id: str = ""
    started_flow_name: str = ""

@dataclass
class CanceledSystemContext(SystemContext):
    """记录被取消的用户 Flow；字段被 system_task_canceled 的模板直接读取。"""
    canceled_flow_id: str = ""
    canceled_flow_name: str = ""

@dataclass
class ResumedSystemContext(SystemContext):
    """记录从 paused_tasks 恢复的用户 Flow；由 resume_flow 分支创建。"""
    resumed_flow_id: str = ""
    resumed_flow_name: str = ""

@dataclass
class CollectSystemContext(SystemContext):
    """临时接管执行权，向用户收集 active_task 所缺少的一个槽位。

    创建者：FlowExecutor 遇到缺值 CollectSlotStep 时创建。
    生命周期：询问话术执行后随状态保存；下一轮 SetSlotsCommand 填中 slot_name 时结束。
    协作：response 来自用户 Flow 的 collect.response，随后通过 system flow 的
    ``args: context.response`` 交给 ActionResponse。
    """

    # 正在等待的槽位名，例如 order_number。
    slot_name: str = ""

    # 来自业务 collect Step 的询问话术配置。
    response: dict[str, Any] = field(default_factory=dict)

# 数据库存的是普通 JSON；此表负责把系统上下文恢复成正确的 dataclass 子类。
mapping_types = {
    "system_task_started": StartedSystemContext,
    "system_task_interrupted": InterruptedSystemContext,
    "system_task_canceled": CanceledSystemContext,
    "system_task_resumed": ResumedSystemContext,
    "system_collect_information": CollectSystemContext,
}
