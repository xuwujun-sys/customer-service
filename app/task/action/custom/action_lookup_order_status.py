"""查询订单详情的自定义 Action，并整理成状态与摘要两个 Flow 槽位。

由用户 Flow 的同名 action 节点调用，下游依赖 commerce_client。输出字段随后由
YAML action_response 模板拼接；特别是 order_summary 必须自带完整句尾。
"""

from typing import Any

from app.domain.dialogue_state import DialogueState
from app.infrastructure import commerce_client
from app.task.action.base import Action, ActionResult


class ActionLookupOrderStatus(Action):
    """查订单详情，填 order_status / order_summary 两个槽位。

    对应 yml 话术：
      订单{{ slots.order_number }}当前状态是：{{ slots.order_status }}。{{ slots.order_summary }}
    所以 order_summary 必须是自带句号的完整句子，失败时也得让这句话读得通。
    """

    name = 'action_lookup_order_status'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """根据 active_task.slots.order_number 查询订单并转换结果。

        缺订单号和接口异常都被转换为可渲染槽位，而不是抛出技术错误。404 与服务
        故障给出不同建议。方法本身不推进 Step，也不直接写槽位。
        """
        slots = state.active_task.slots if state.active_task else {}
        order_number = str(slots.get("order_number") or "").strip()

        if not order_number:
            return ActionResult(slot_updates={
                "order_status": "缺少订单号",
                "order_summary": "请先把订单号发我，我才能查。",
            })

        try:
            data = await commerce_client.get_data(f"/orders/{order_number}")
        except commerce_client.CommerceError as exc:
            reason = str(exc.message).rstrip("。")
            # 订单查不到 vs 服务本身有问题，给用户的下一步建议不一样
            hint = ("如果订单号是手动输入的，可以核对一下再发我一次。"
                    if exc.status_code == 404
                    else "可以过一会儿再试一次，需要的话我帮你转人工客服。")
            return ActionResult(slot_updates={
                "order_status": f"暂时查不到（{reason}）",
                "order_summary": hint,
            })

        return ActionResult(slot_updates={
            "order_status": str(data.get("status") or "未知"),
            "order_summary": _build_summary(data),
        })


def _build_summary(data: dict[str, Any]) -> str:
    """把订单接口结构整理成可直接接在状态后的自然语言摘要。

    输入是接口 JSON；输出可能包含金额、时间、前两项商品与商家状态说明。函数
    只做纯数据转换，便于独立测试，且保证非空摘要以中文句号结束。
    """
    parts: list[str] = []

    amount = data.get("amount")
    if amount:
        parts.append(f"金额 {amount} 元")

    created_at = str(data.get("created_at") or "")
    if created_at:
        parts.append(f"{created_at.replace('T', ' ')[:16]} 下单")

    items = data.get("items") or []
    if items:
        # 标题只展示前两项以控制长度，但件数统计覆盖全部明细。
        titles = "、".join(str(item.get("title") or "") for item in items[:2])
        quantity = sum(int(item.get("quantity") or 0) for item in items)
        more = f" 等 {quantity} 件" if len(items) > 2 else ""
        parts.append(f"商品是{titles}{more}")

    summary = "，".join(parts)
    desc = str(data.get("status_desc") or "").rstrip("。")
    if desc:
        summary = f"{summary}。{desc}" if summary else desc

    return f"{summary}。" if summary else ""
