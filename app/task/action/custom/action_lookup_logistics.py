"""查询订单物流的自定义 Action，并把接口结果转换为 Flow 使用的槽位。

上游 YAML 的 ``action_lookup_logistics`` 节点通过 Registry/Runner 调用本类；下游
是 commerce_client 的订单物流接口。返回的三个槽位随后被同一 Flow 的
action_response Jinja 模板读取，字段名和标点约定不能单独修改。
"""

from typing import Any

from app.domain.dialogue_state import DialogueState
from app.infrastructure import commerce_client
from app.task.action.base import Action, ActionResult


class ActionLookupLogistics(Action):
    """查物流，填 tracking_number / logistics_company / logistics_status 三个槽位。

    对应 yml 话术：
      订单{{ slots.order_number }}由{{ slots.logistics_company }}配送，物流单号是{{ slots.tracking_number }}。当前进度：{{ slots.logistics_status }}。
    模板自己补了句尾的「。」，所以 logistics_status 不能再带句号。
    """

    name = 'action_lookup_logistics'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """按 active_task 中的订单号查询物流并返回槽位更新。

        ``action_kwargs`` 当前未使用，但保留以满足 Action 统一协议。接口成功时
        规范化承运商、运单号、状态；失败时调用辅助函数补查订单状态，使回复更
        容易解释。方法不直接写 state，由 FlowExecutor 统一合并 slot_updates。
        """
        # 业务 Action 只应从当前用户任务取订单号，系统 Context 不承载业务槽位。
        slots = state.active_task.slots if state.active_task else {}
        order_number = str(slots.get("order_number") or "").strip()

        if not order_number:
            return ActionResult(slot_updates={
                "tracking_number": "暂无",
                "logistics_company": "暂无",
                "logistics_status": "缺少订单号，请先把订单号发我",
            })

        try:
            data = await commerce_client.get_data(f"/orders/{order_number}/logistics")
        except commerce_client.CommerceError as exc:
            return ActionResult(slot_updates=await _no_logistics_updates(order_number, exc))

        # 物流轨迹约定最新一项在首位；无轨迹时退回接口的 status_desc。
        traces = data.get("traces") or []
        latest = str(traces[0].get("desc") or "") if traces else str(data.get("status_desc") or "")
        status = str(data.get("status") or "")
        progress = f"{status}，{latest}" if latest and latest != status else (status or latest)

        return ActionResult(slot_updates={
            "tracking_number": str(data.get("tracking_number") or "暂无"),
            "logistics_company": str(data.get("logistics_company") or "暂无"),
            "logistics_status": progress.rstrip("。"),
        })


async def _no_logistics_updates(order_number: str, exc: commerce_client.CommerceError) -> dict[str, str]:
    """没查到物流时再补一刀订单状态，把「为什么没有物流」说清楚。

    yml 那句模板是写死的，改不了，所以这里只能尽量让「当前进度：」后面那句完整可读。
    """
    # 先保留物流接口的原始业务原因，再尝试用订单状态补充上下文。
    reason = str(exc.message or "").rstrip("。")
    try:
        order = await commerce_client.get_data(f"/orders/{order_number}")
        status = str(order.get("status") or "")
        if status:
            reason = f"该订单当前状态为{status}，{reason}" if reason else f"该订单当前状态为{status}"
    except commerce_client.CommerceError:
        # 补查失败不覆盖第一次错误；仍返回结构完整、可供模板渲染的槽位。
        pass

    return {
        "tracking_number": "暂无",
        "logistics_company": "暂无",
        "logistics_status": reason or "暂时没有可查询的物流信息",
    }
