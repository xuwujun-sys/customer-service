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
    reason = str(exc.message or "").rstrip("。")
    try:
        order = await commerce_client.get_data(f"/orders/{order_number}")
        status = str(order.get("status") or "")
        if status:
            reason = f"该订单当前状态为{status}，{reason}" if reason else f"该订单当前状态为{status}"
    except commerce_client.CommerceError:
        pass

    return {
        "tracking_number": "暂无",
        "logistics_company": "暂无",
        "logistics_status": reason or "暂时没有可查询的物流信息",
    }
