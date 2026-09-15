"""把用户/系统 YAML 配置加载成可共享执行的 Flow、Step、Slot 对象。

本模块只在应用启动的装配根中运行，负责配置解析和对象构造，不负责推进流程。
其输出同时被 Planner（能力菜单）、CommandProcessor（创建任务）和 FlowExecutor
（解释执行）使用。YAML 字段、Step.from_dict 与本 Loader 必须保持一致。
"""

from pathlib import Path

import yaml

from app.task.flow.models import FlowsList, FlowSlot, Flow
from app.task.flow.steps import FlowStep, FlowStepType, mapping_types


class FlowLoader:
    """将一份或多份受信任 YAML Flow 配置转换为 ``FlowsList``。

    实例无状态，通常在 ``build_dialogue_engine`` 中短暂创建。配置问题会在应用
    启动阶段暴露，避免服务运行后才在某个用户请求中失败。
    """

    def load(self, path: Path) -> FlowsList:
        """加载单个 YAML 文件并返回其中的槽位和流程。

        参数 ``path`` 必须指向项目受信任配置；返回对象已完成 Step 子类转换。
        """
        # 单文件加载入口；safe_load 避免执行 YAML 中的任意 Python 对象。
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        slots = self._load_slots(data.get("slots", {}))
        flows = self._load_flows(data.get("flows", {}), slots)

        return FlowsList(flows, slots)

    def load_many(self, paths: list[Path]) -> FlowsList:
        """合并多份 YAML，使用户 Flow 与系统辅助 Flow 能互相引用。

        后读取文件的同名 slot/flow 覆盖前者。项目当前顺序是 user_flows 后
        system_flows；新增同名 ID 时要意识到覆盖行为。
        """
        all_slots: dict[str, FlowSlot] = {}
        all_flows_data: dict[str, dict] = {}

        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            slots_data = data.get("slots", {})
            flows_data = data.get("flows", {})

            # 后加载的同名配置会覆盖先加载的配置。
            loaded_slots = self._load_slots(slots_data)
            all_slots.update(loaded_slots)

            all_flows_data.update(flows_data)

        # 先合并全局 Slot，再创建引用这些 Slot 的 Flow。
        flows = self._load_flows(
            flows=all_flows_data,
            slots=all_slots,
        )

        return FlowsList(
            flows,
            all_slots,
        )

    def _load_slots(
        self,
        slots: dict[str, dict],
    ) -> dict[str, FlowSlot]:
        """把 YAML ``slots`` 映射成以槽位名索引的 FlowSlot 字典。"""
        myslots: dict[str, FlowSlot] = {}

        for slot_name, slot in slots.items():
            # YAML 外层键就是 name，其余 type/label/description 从内部字段展开。
            myslots[slot_name] = FlowSlot(
                **slot,
                name=slot_name,
            )

        return myslots

    def _load_flows(
        self,
        flows: dict[str, dict],
        slots: dict[str, FlowSlot],
    ) -> list[Flow]:
        """根据 ``step.type`` 构造节点子类，并组装每条 Flow。

        collect 节点引用的 slot_name 必须先存在于合并后的 slots 字典；Action 节点
        的 action 名要在 ActionRegistry 注册，但该关联在运行 Action 时才验证。
        """
        myflows: list[Flow] = []

        for flow_id, flow_data in flows.items():
            # mapping_types 将 start/collect/action/end 映射为对应 dataclass。
            steps: list[FlowStep] = [
                mapping_types[step_data["type"]].from_dict(step_data)
                for step_data in flow_data["steps"]
            ]

            myslots: list[FlowSlot] = []

            # Flow.slots 只保留该 Flow 的 collect Steps 实际依赖的槽位。
            for step in steps:
                if step.type == FlowStepType.COLLECT:
                    myslots.append(slots[step.slot_name])

            flow = Flow(
                id=flow_id,
                name=flow_data["name"],
                description=flow_data["description"],
                slots=myslots,
                steps=steps,
            )

            myflows.append(flow)

        return myflows


# 直接运行本文件时的人工解析演示；导入模块或启动 FastAPI 时不会执行。
if __name__ == "__main__":
    root = Path(__file__).parents[3]
    flow_config_dir = root / "flow_config"

    paths = [
        flow_config_dir / "user_flows.yml",
        flow_config_dir / "system_flows.yml",
    ]

    loader = FlowLoader()
    flows = loader.load_many(paths)

    print(flows)
