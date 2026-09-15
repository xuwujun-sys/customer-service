"""KnowledgeProvider 的 ID 注册表。

KnowledgeIntent 只保存 provider_id；KnowledgeHandler 通过本表找到真实 Provider。
实际 Provider 列表由 ``build_dialogue_engine`` 显式注入。
"""

from app.knowledge.provider import KnowledgeProvider, ProductAPIProvider, OrderAPIProvider, RAGProvider, \
    FAQProvider


class KnowledgeProviderRegistry:
    """保存可跨请求复用的 Provider 实例并提供按 ID 查询。"""

    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        """把 Provider 列表建立成 ID 索引；同 ID 后项会覆盖前项。"""
        self._providers_by_id = {p.provider_id: p for p in providers}

    def get(self, provider_id: str) -> KnowledgeProvider:
        """返回指定 Provider；未注册 ID 会明确抛 KeyError。"""
        return self._providers_by_id[provider_id]


# 直接运行时用于人工验证构造，不属于服务运行路径。
if __name__ == '__main__':
    registry = KnowledgeProviderRegistry([ProductAPIProvider(), OrderAPIProvider(), RAGProvider(), FAQProvider()])
