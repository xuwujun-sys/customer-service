from pathlib import Path

import yaml

from app.task.flow.models import FlowsList, FlowSlot, Flow
from app.task.flow.steps import FlowStep, FlowStepType, mapping_types


class FlowLoader:
    def load(self, path: Path) -> FlowsList:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        slots = self._load_slots(data.get("slots", {}))
        flows = self._load_flows(data.get("flows", {}), slots)

        return FlowsList(flows, slots)

    def load_many(self, paths: list[Path]) -> FlowsList:
        all_slots: dict[str, FlowSlot] = {}
        all_flows_data: dict[str, dict] = {}

        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            slots_data = data.get("slots", {})
            flows_data = data.get("flows", {})

            loaded_slots = self._load_slots(slots_data)
            all_slots.update(loaded_slots)

            all_flows_data.update(flows_data)

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
        myslots: dict[str, FlowSlot] = {}

        for slot_name, slot in slots.items():
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
        myflows: list[Flow] = []

        for flow_id, flow_data in flows.items():
            steps: list[FlowStep] = [
                mapping_types[step_data["type"]].from_dict(step_data)
                for step_data in flow_data["steps"]
            ]

            myslots: list[FlowSlot] = []

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