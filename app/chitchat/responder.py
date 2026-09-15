"""闲聊文本生成器：使用独立 Prompt 回答非业务、非知识类消息。

它只负责自然语言生成，不接触 Flow、Command 或任务状态。上游 ChitchatHandler
提供当前消息和已完成历史，返回格式与其他轨道一致。
"""

import asyncio

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_service_domain import *
from app.domain.dialogue_state import *
from app.infrastructure.llm import llm
from app.prompts.build_history import BuildHistory
from app.prompts.load_prompt import load_prompt

class ChitchatResponder:
    """把当前话语与近期历史渲染进闲聊 Prompt，并调用共享 LLM。"""

    async def respond(
            self,
            user_message: Message,
            recent_turns: list[Turn],
    ) -> list[BotMessage]:
        """异步生成一条闲聊回复。

        参数分别为当前领域消息与不含当前轮的历史 Turn；返回单条 BotMessage。
        本方法无状态副作用。
        """
        user_message = self.get_user_message(user_message)
        history = BuildHistory.build_history(recent_turns)

        prompt_text = load_prompt("chitchat_prompts")
        prompt = PromptTemplate.from_template(
            prompt_text,
            template_format="jinja2"
        )
        chain = prompt | llm | StrOutputParser()
        response = await chain.ainvoke({
            "user_message": user_message,
            "history": history,
        })
        return [BotMessage(text=response)]

    def get_user_message(self, user_message):
        """将文本/对象消息转换为 Prompt 字符串。"""
        if user_message.type == MessageType.TEXT:
            return user_message.text
        elif user_message.type == MessageType.OBJECT:
            return str(user_message.object.to_dict())


# 直接运行时的 LLM 联调示例，服务导入时不执行。
if __name__ == '__main__':
    chitchat_responder = ChitchatResponder()


    async def test():
        response = await chitchat_responder.respond(
            user_message=Message(
                sender_id="u1001",
                message_id="m1001",
                type=MessageType.TEXT,
                text="你好"
            ),
            recent_turns=[]
        )
        print(response)


    asyncio.run(test())
