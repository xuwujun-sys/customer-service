"""内存中的 Flow/Slot 聚合模型及其查询接口。

FlowLoader 将 YAML 转为本模块对象；TurnPlanner 读取 Flow 的元数据向 LLM 展示
能力菜单；CommandProcessor 与 FlowExecutor 则用 flow_id/step_id 查找执行节点。
因此这些类是“配置定义、规划、运行时”三部分共同依赖的数据合同。
"""

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from app.task.flow.steps import (
    CollectSlotStep,
    FlowStep,
    FlowStepType,
    StartFlowStep,
)


@dataclass(slots=True)
class FlowSlot:
    """一个业务槽位的元数据定义。

    ``name`` 是 TaskContext.slots 的键，也是 YAML CollectSlotStep.slot_name 的值；
    label/description 用于向规划器解释含义，type 当前主要是描述信息。
    """
    name: str
    type: str = "any"
    label: str = ""
    description: str = ""


@dataclass(slots=True)
class Flow:
    """一条完整可执行工作流，包含元数据、依赖槽位和有向 Step 列表。

    由 FlowLoader 在应用启动时创建并长期只读共享。运行游标不放在这里，而放在
    每位用户自己的 TaskContext.step_id 中，因此多个用户可安全执行同一 Flow。
    """
    id: str
    description: str = ""
    steps: List[FlowStep] = field(default_factory=list)
    slots: List[FlowSlot] = field(default_factory=list)
    name: str | None = None

    def readable_name(self) -> str:
        """优先返回面向用户的名称，未配置时以稳定 id 兜底。"""
        return self.name or self.id

    def step_by_id(self, step_id: str | None) -> Optional[FlowStep]:
        """按运行时游标查找 Step；游标为空或不存在时返回 None。"""
        if step_id is None:
            return None
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def start_step(self) -> Optional[StartFlowStep]:
        """返回首个 StartFlowStep，供 start/resume 逻辑建立初始 TaskContext。"""
        for step in self.steps:
            if isinstance(step, StartFlowStep):
                return step
        return None

    def collect_steps(self) -> List[CollectSlotStep]:
        """返回本 Flow 的所有收集节点，主要用于能力描述和配置分析。"""
        return [
            step for step in self.steps if isinstance(step, CollectSlotStep)
        ]

@dataclass(slots=True)
class FlowsList:
    """用户 Flow 与系统 Flow 的只读聚合集合。

    ``flows`` 用于按 ID 找流程，``slots`` 保存合并后的全局槽位定义。它由
    FlowLoader.load_many 创建并注入 Planner、TaskHandler、Executor。
    """
    flows: List[Flow] = field(default_factory=list)
    slots: Dict[str, FlowSlot] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Flow]:
        """允许直接 ``for flow in flows_list`` 遍历。"""
        return iter(self.flows)

    def __len__(self) -> int:
        """返回已加载 Flow 数量。"""
        return len(self.flows)

    def flow_by_id(self, flow_id: str) -> Optional[Flow]:
        """按稳定 ID 查 Flow；调用方目前通常假设结果一定存在。"""
        for flow in self.flows:
            if flow.id == flow_id:
                return flow
        return None

    def slot_by_name(self, slot_name: str) -> Optional[FlowSlot]:
        """从合并后的槽位索引中查定义，不修改集合。"""
        return self.slots.get(slot_name)
