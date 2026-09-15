"""知识问答轨道的意图能力清单。

该清单同时提供给 TurnPlanner（限制 LLM 只能选已知意图）、Validator（检查是否
需要聚焦商品/订单）和 KnowledgeHandler（将意图映射到 Provider）。它是三者的
共享配置合同；新增意图时必须确认 provider_id 已在装配根注册。
"""

from dataclasses import dataclass, field


@dataclass
class KnowledgeIntent:
    """一类知识问题的元数据。

    id 是 Prompt 输出值；description 帮助 LLM 判断；provider_ids 决定检索来源；
    requires_object 声明是否必须已有特定类型的 focused_object。
    """
    id: str
    description: str
    provider_ids: list[str] = field(default_factory=list)
    requires_object: str | None = None


# 进程级只读意图表；外层字典键应与每个 KnowledgeIntent.id 保持一致。
KNOWLEDGE_INTENTS: dict[str, KnowledgeIntent] = {
    "product_info": KnowledgeIntent(
        id="product_info",
        description="商品信息咨询",
        provider_ids=["api.product"],
        requires_object="product",
    ),
    "order_info": KnowledgeIntent(
        id="order_info",
        description="订单信息咨询",
        provider_ids=["api.order"],
        requires_object="order",
    ),
    "refund_policy": KnowledgeIntent(
        id="refund_policy",
        description="退款政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "return_policy": KnowledgeIntent(
        id="return_policy",
        description="退货政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "shipping_policy": KnowledgeIntent(
        id="shipping_policy",
        description="配送政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    "platform_rule": KnowledgeIntent(
        id="platform_rule",
        description="平台规则咨询",
        # 当前同一 Provider 被重复配置；Handler 最终会去重，但这里可视为配置瑕疵。
        provider_ids=["rag.default", "rag.default"],
    ),
    "general_ecommerce_info": KnowledgeIntent(
        id="general_ecommerce_info",
        description="电商通用信息咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
}
