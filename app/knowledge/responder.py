import asyncio

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_service_domain import BotMessage, MessageType
from app.domain.dialogue_state import Turn, Message
from app.infrastructure.llm import llm
from app.knowledge.provider import KnowledgeChunk
from app.prompts import build_history
from app.prompts.load_prompt import load_prompt


class KnowledgeResponder:
    async def respond(
            self,
            user_message: Message,
            recent_turns: list[Turn],
            chunks: list[KnowledgeChunk],
    ) -> list[BotMessage]:
        user_message = self.get_user_message(user_message)
        recent_message = build_history.BuildHistory.build_history(recent_turns)
        knowledge_chunk = "\n\n".join(chunk.content for chunk in chunks)

        prompt = load_prompt("knowledge_prompts")
        prompt_template = PromptTemplate.from_template(
            prompt,
            template_format="jinja2"
        )

        chain = prompt_template | llm | StrOutputParser()

        res = await chain.ainvoke({
            "user_message": user_message,
            "history": recent_message,
            "knowledge_content": knowledge_chunk,
        })

        return [BotMessage(text=res)]

    def get_user_message(self, user_message):
        if user_message.type == MessageType.TEXT:
            return user_message.text
        elif user_message.type == MessageType.OBJECT:
            return str(user_message.object.to_dict())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    responder = KnowledgeResponder()

    async def test():
        user_message = Message(
            message_id="m100",
            sender_id="user001",
            type=MessageType.TEXT,
            text="这款笔记本有什么颜色可选？",
        )
        recent_turns = [
            Turn(
                turn_id="t1",
                user_message=Message(
                    message_id="m99",
                    sender_id="user001",
                    type=MessageType.TEXT,
                    text="你好，我想买电脑",
                ),
                bot_messages=[BotMessage(text="你好！请问有什么可以帮您？")],
            )
        ]
        chunks = [
            KnowledgeChunk(content="商品：轻薄笔记本 X1，颜色有银色、深空灰，价格 5999 元。"),
        ]

        res = await responder.respond(
            user_message=user_message,
            recent_turns=recent_turns,
            chunks=chunks,
        )
        print("BotMessage 数量:", len(res))
        print("回复:", res[0].text)

    asyncio.run(test())
