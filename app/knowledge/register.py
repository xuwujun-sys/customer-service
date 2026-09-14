from app.knowledge.provider import KnowledgeProvider, ProductAPIProvider, OrderAPIProvider, RAGProvider, \
    FAQProvider


class KnowledgeProviderRegistry:
    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        self._providers_by_id = {p.provider_id: p for p in providers}

    def get(self, provider_id: str) -> KnowledgeProvider:
        return self._providers_by_id[provider_id]


if __name__ == '__main__':
    registry = KnowledgeProviderRegistry([ProductAPIProvider(), OrderAPIProvider(), RAGProvider(), FAQProvider()])
