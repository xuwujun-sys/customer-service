import asyncio

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_service_domain import *
from app.domain.dialogue_state import *
from app.infrastructure.llm import llm
from app.prompts.build_history import BuildHistory
from app.prompts.load_prompt import load_prompt

class ChitchatResponder:

    async def respond(
            self,
            user_message: Message,
            recent_turns: list[Turn],
    ) -> list[BotMessage]:
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
        if user_message.type == MessageType.TEXT:
            return user_message.text
        elif user_message.type == MessageType.OBJECT:
            return str(user_message.object.to_dict())


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
