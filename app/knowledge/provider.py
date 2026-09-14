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
    content: str


class KnowledgeProvider(ABC):
    provider_id = ""

    @abstractmethod
    async def retrieve(
        self,
        state: DialogueState,
    ) -> list[KnowledgeChunk]:
        return []

class ProductAPIProvider(KnowledgeProvider):
    provider_id = 'api.product'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        product_id = state.focused_object.id
        data: dict[str, Any] = await self.get_product_by_id(product_id)
        text = json.dumps(data,ensure_ascii=False,indent=2)
        return [KnowledgeChunk(content=f"商品信息\n{text}")]


    async def get_product_by_id(self, product_id: str):
        url = f"{settings.commerce_api_base_url}/products/{product_id}"
        response = await http_client.client.get(url)
        return response.json()["data"]
class OrderAPIProvider(KnowledgeProvider):
    provider_id = 'api.order'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        focused_object = state.focused_object
        order_number = focused_object.id

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
        url = f"{settings.commerce_api_base_url}/orders/{order_number}"
        response = await http_client.client.get(url)
        return response.json()["data"]

    async def _fetch_logistics(self, order_number) -> dict[str, Any]:
        url = f"{settings.commerce_api_base_url}/orders/{order_number}/logistics"
        response = await http_client.client.get(url)
        return response.json().get("data", {})


class FAQProvider(KnowledgeProvider):
    provider_id = 'faq.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        return [KnowledgeChunk(content="未检索到相关问题")]


class RAGProvider(KnowledgeProvider):
    provider_id = 'rag.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        return [KnowledgeChunk(content="未检索到相关信息")]

if __name__ == "__main__":
    state = DialogueState(sender_id="uer001", focused_object=FocusedObject(type="product",id="SKU10001"))
    provider = ProductAPIProvider()

    async def test():
        res = await provider.retrieve(state)
        print(res[0].content)
        await http_client.close_client()

    asyncio.run(test())









