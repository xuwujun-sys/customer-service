"""Knowledge 轨道编排：知识意图 -> Provider -> Chunk -> 自然语言回复。

上游 Engine 在进入本轨道前会暂停活动业务任务；本模块不再处理任务状态，只将
规划意图映射成检索来源，聚合资料后交给 Responder。它不直接理解 API/RAG 细节。
"""

from app.domain.dialogue_state import BotMessage, DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.knowledge.provider import KnowledgeChunk
from app.knowledge.register import KnowledgeProviderRegistry
from app.knowledge.responder import KnowledgeResponder


class KnowledgeHandler:
    """协调意图元数据、Provider Registry 和 LLM Responder。

    由装配根创建并长期复用，三个依赖均为进程级组件。每次 handle 的用户上下文
    完全来自参数 state。
    """
    def __init__(self, knowledge_intents: dict[str, KnowledgeIntent],
                 provider_registry: KnowledgeProviderRegistry,
                 knowledge_responder: KnowledgeResponder):
        """注入知识能力表、检索器注册表和答案生成器。"""
        self.knowledge_intents = knowledge_intents
        self.provider_registry = provider_registry
        self.knowledge_responder = knowledge_responder

    async def handle(self, intents: list[str], state: DialogueState) -> list[BotMessage]:
        """检索规划意图需要的全部资料，并生成本轮知识回答。

        参数:
            intents: Planner 选择且 Validator 检查过非空的意图 ID；
            state: 提供 focused_object、当前用户消息和历史。
        返回:
            KnowledgeResponder 生成的 BotMessage 列表。

        当前 Provider 按顺序调用；某个 Provider 抛异常会终止整个回答且本轮状态
        不提交。若需部分成功，应在这里引入并发及逐来源异常隔离。
        """
        # 一个意图可对应多个 Provider，多个意图的 Provider 会去重。
        provider_ids: list[str] = self._get_provider_ids_by_intents(intents)

        # 依次检索知识；每个 Provider 返回统一的 KnowledgeChunk。
        chunks: list[KnowledgeChunk] = []
        for provider_id in provider_ids:
            provider = self.provider_registry.get(provider_id)
            current_chunks = await provider.retrieve(state)
            chunks.extend(current_chunks)

        # Responder 只基于用户问题、历史和检索资料组织自然语言。
        return await self.knowledge_responder.respond(
            user_message=state.pending_turn.user_message,
            recent_turns=state.current_session().turns,
            chunks=chunks
        )

    def _get_provider_ids_by_intents(self, intents: list[str]) -> list[str]:
        """展开每个意图的 Provider ID，并去除重复来源。

        当前通过 set 去重，结果顺序不稳定；若知识片段顺序会影响模型回答，应改为
        保序去重。未知 intent 会在字典查找处抛 KeyError。
        """
        provider_ids: list[str] = []
        for intent in intents:
            provider_ids.extend(self.knowledge_intents[intent].provider_ids)
        return list(set(provider_ids))
