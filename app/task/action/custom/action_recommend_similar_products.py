"""在现有电商接口能力上实现可解释的相似商品推荐 Action。

项目没有专门推荐接口，因此先查当前商品，再从用户最近商品构造候选池，并发查询
详情后按属性相似度、价格差排序。不同于查询型 Action，本 Flow 后面直接 end，
所以本动作自行产生 BotMessage 而非只返回槽位。
"""

import asyncio
from typing import Any

from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.infrastructure import commerce_client
from app.task.action.base import Action, ActionResult

# 最多展示三项，避免客服回复过长；最多并发查询八个候选，限制外部接口压力。
TOP_N = 3
MAX_CANDIDATES = 8


class ActionRecommendSimilarProducts(Action):
    """基于商品属性重合度推荐相似商品。

    电商服务没有「相似商品」接口，也列不出全站商品，唯一可用的候选池是
    /users/{user_id}/products（用户最近商品）。所以策略是：
      当前商品 attributes ←→ 候选商品 attributes，比有多少个同名同值的属性。
    匹配到的属性名会写进回复，让推荐理由对用户可见，而不是凭空甩三个商品。

    yml 里这个步骤后面直接是 end，没有 action_response，话术由本动作自己产出。
    """

    name = 'action_recommend_similar_products'

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """从槽位/聚焦对象取得商品 ID，构造候选并返回可解释推荐文本。

        参数 ``action_kwargs`` 当前未使用。输入数据来自 active_task.slots、
        focused_object 和 sender_id；返回只含消息、不更新槽位。
        """
        slots = state.active_task.slots if state.active_task else {}
        product_id = str(slots.get("product_id") or "").strip()

        # Collect Step 通常已自动补槽；这里再次使用 focused_object 是防御性兜底。
        if not product_id and state.focused_object is not None and state.focused_object.type == "product":
            product_id = str(state.focused_object.id or "").strip()

        if not product_id:
            return self._message("你先告诉我想了解哪个商品，我再帮你找相近的。")

        try:
            current = await commerce_client.get_data(f"/products/{product_id}")
        except commerce_client.CommerceError as exc:
            reason = str(exc.message).rstrip("。")
            # 服务返回的话里常带商品号，别重复念两遍
            text = f"{reason}。" if product_id in reason else f"商品 {product_id} 我暂时查不到：{reason}。"
            return self._message(text)

        try:
            history = await commerce_client.get_data(f"/users/{state.sender_id}/products")
        except commerce_client.CommerceError:
            # 电商服务里没有这个用户的历史记录，没有候选池可用，只能介绍当前商品本身
            return self._message(_describe(current, prefix="暂时找不到可对比的商品，先看下这款："))

        candidates = [
            item for item in (history.get("products") or [])
            if str(item.get("product_id") or "") and str(item.get("product_id")) != product_id
        ]
        if not candidates:
            return self._message(
                f"暂时没有帮你找到和{_title(current)}相近的商品。" + _describe(current, prefix="这款本身是：")
            )

        # 候选详情互不依赖，并发查询可避免串行网络等待成倍增加响应时间。
        details = await asyncio.gather(*[
            _safe_detail(str(item["product_id"])) for item in candidates[:MAX_CANDIDATES]
        ])
        scored = [(detail, _similarity(current, detail)) for detail in details if detail]
        if not scored:
            return self._message(
                f"暂时没有帮你找到和{_title(current)}相近的商品。" + _describe(current, prefix="这款本身是：")
            )

        # 至少共享一个属性维度才称为“规格相近”，否则明确降级为价格近似。
        matched = [item for item in scored if item[1][0] > 0]
        if matched:
            matched.sort(key=lambda item: (-item[1][0], _price_gap(current, item[0])))
            picked, lead = matched[:TOP_N], f"结合你最近看过的商品，和{_title(current)}比较接近的有："
        else:
            # 连一个相同规格维度都没有，退一步按价格最接近的给，并说清楚理由只有价格
            scored.sort(key=lambda item: _price_gap(current, item[0]))
            picked, lead = scored[:TOP_N], f"没找到和{_title(current)}规格相近的，按价格最接近给你几个参考："

        lines = [
            f"{index}. {item[0].get('title')}（{item[0].get('price')} 元）{_reason_text(item[1])}"
            for index, item in enumerate(picked, start=1)
        ]

        return self._message(lead + "\n" + "\n".join(lines))

    @staticmethod
    def _message(text: str) -> ActionResult:
        """把纯文本统一包装成 ActionRunner 约定的消息结果。"""
        return ActionResult(messages=[BotMessage(text=text)])


async def _safe_detail(product_id: str) -> dict[str, Any] | None:
    """查询单个候选详情；某一候选失败时返回 None，不中断整批推荐。"""
    try:
        return await commerce_client.get_data(f"/products/{product_id}")
    except commerce_client.CommerceError:
        return None


def _similarity(current: dict[str, Any], other: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    """属性相似度：同名同值算 2 分，同名不同值（如都是「容量」）算 1 分。

    电商服务里 5 个商品没有任何一对属性是完全相等的（iPhone 的颜色是远峰蓝、
    Watch 的是午夜色），只按完全相等打分的话相似度恒为 0，推荐会永远退化成
    按价格排。同名属性本身就说明是同一类规格维度，所以给它一半的分。
    返回 (得分, 取值一致的属性名, 仅维度相同的属性名)，两个名单都会用于说明推荐理由。
    """
    current_attrs = current.get("attributes") or {}
    other_attrs = other.get("attributes") or {}

    exact_names = [
        name for name, value in current_attrs.items()
        if name in other_attrs and str(other_attrs[name]).strip() == str(value).strip()
    ]
    same_key_names = [
        name for name in current_attrs
        if name in other_attrs and name not in exact_names
    ]
    return 2 * len(exact_names) + len(same_key_names), exact_names, same_key_names


def _price_gap(current: dict[str, Any], other: dict[str, Any]) -> float:
    """计算价格绝对差；无法转换的价格排到候选末尾。"""
    try:
        return abs(float(current.get("price") or 0) - float(other.get("price") or 0))
    except (TypeError, ValueError):
        return float("inf")


def _reason_text(similarity: tuple[int, list[str], list[str]]) -> str:
    """把打分依据写成给用户看的理由，取值一致优先于仅维度相同。"""
    _, exact_names, same_key_names = similarity
    if exact_names:
        return f"，相似点：{'、'.join(exact_names)}（取值一致）"
    if same_key_names:
        return f"，规格维度相同：{'、'.join(same_key_names)}"
    return ""


def _title(product: dict[str, Any]) -> str:
    """生成回复中引用当前商品的短标题，缺标题时使用通用占位。"""
    return f"《{product.get('title') or '这个商品'}》"


def _describe(product: dict[str, Any], prefix: str = "") -> str:
    """将商品标题、价格、库存和描述压缩为一段自然语言。"""
    bits = [str(product.get("title") or ""), f"售价 {product.get('price')} 元"]
    if product.get("stock_status"):
        bits.append(str(product["stock_status"]))
    detail = "，".join(bit for bit in bits if bit)
    description = str(product.get("description") or "").strip()
    text = f"{detail}。{description}" if description else f"{detail}。"
    return f"{prefix}{text}" if prefix else text
