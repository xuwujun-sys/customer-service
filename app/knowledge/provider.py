"""知识检索 Provider 接口及商品、订单、FAQ、RAG 四种实现。

KnowledgeHandler 只处理统一的 KnowledgeChunk，不关心资料来自 HTTP、FAQ 还是
向量检索。商品/订单 Provider 依赖 focused_object 的 ID；FAQ/RAG 当前只是占位，
尚未接入真实知识库。
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import json

from app.domain.dialogue_state import DialogueState, FocusedObject
from app.config.config import settings
import app.infrastructure.http_client as http_client


@dataclass
class KnowledgeChunk:
    """提供给 KnowledgeResponder 的最小检索结果单位，当前只含文本内容。"""
    content: str


class KnowledgeProvider(ABC):
    """所有知识来源的抽象接口。

    子类声明唯一 provider_id 并实现异步 retrieve。实例在 Engine 装配时创建并
    长期复用，不应持有某位用户的状态。
    """
    provider_id = ""

    @abstractmethod
    async def retrieve(
        self,
        state: DialogueState,
    ) -> list[KnowledgeChunk]:
        """根据当前对话上下文检索零到多个知识片段。"""
        return []

class ProductAPIProvider(KnowledgeProvider):
    """根据 focused_object.id 从电商 HTTP 接口检索商品详情。"""
    provider_id = 'api.product'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """查询聚焦商品，并把结构化 JSON 包装成供 LLM 阅读的知识文本。"""
        product_id = state.focused_object.id
        data: dict[str, Any] = await self.get_product_by_id(product_id)
        text = json.dumps(data,ensure_ascii=False,indent=2)
        return [KnowledgeChunk(content=f"商品信息\n{text}")]


    async def get_product_by_id(self, product_id: str):
        """调用商品详情接口并取响应信封中的 data。

        当前直接使用共享 http_client，未复用 commerce_client 的统一状态码、网络
        异常和响应结构处理；接口失败可能以裸异常终止本轮，这是可改进点。
        """
        url = f"{settings.commerce_api_base_url}/products/{product_id}"
        response = await http_client.client.get(url)
        return response.json()["data"]
class OrderAPIProvider(KnowledgeProvider):
    """并发查询聚焦订单的详情与物流，并合并为一个知识片段。"""
    provider_id = 'api.order'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """读取订单对象 ID，并发获取两个互不依赖的 HTTP 结果。"""
        focused_object = state.focused_object
        order_number = focused_object.id

        # 并发等待可把总延迟压到两次请求中较慢的一次附近。
        order_payload, logistics_payload = await asyncio.gather(
            self._fetch_order(order_number),
            self._fetch_logistics(order_number),
        )

        return [
            KnowledgeChunk(
                content="订单与物流信息：\n"
                        + json.dumps(
                    {
                        "order_number": order_number,
                        "order": order_payload,
                        "logistics": logistics_payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        ]

    async def _fetch_order(self, order_number) -> dict[str, Any]:
        """调用订单详情接口并返回 data；异常当前直接向上传播。"""
        url = f"{settings.commerce_api_base_url}/orders/{order_number}"
        response = await http_client.client.get(url)
        return response.json()["data"]

    async def _fetch_logistics(self, order_number) -> dict[str, Any]:
        """调用物流接口；信封中没有 data 时以空字典兜底。"""
        url = f"{settings.commerce_api_base_url}/orders/{order_number}/logistics"
        response = await http_client.client.get(url)
        return response.json().get("data", {})


class FAQProvider(KnowledgeProvider):
    """FAQ 检索占位实现；目前没有按用户问题真正搜索 FAQ。"""
    provider_id = 'faq.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """返回固定占位片段，提示尚未检索到 FAQ。"""
        return [KnowledgeChunk(content="未检索到相关问题")]


class RAGProvider(KnowledgeProvider):
    """RAG/向量知识库占位实现；当前未连接向量数据库。"""
    provider_id = 'rag.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """返回固定占位片段，接口形状为未来真实 RAG 保留。"""
        return [KnowledgeChunk(content="未检索到相关信息")]

# 直接运行文件时的手工联调代码；生产导入不会执行。
if __name__ == "__main__":
    state = DialogueState(sender_id="uer001", focused_object=FocusedObject(type="product",id="SKU10001"))
    provider = ProductAPIProvider()

    async def test():
        res = await provider.retrieve(state)
        print(res[0].content)
        await http_client.close_client()

    asyncio.run(test())









