
from app.domain.dialogue_state import Turn


class BuildHistory:

    @staticmethod
    def build_history(turns: list[Turn]) -> str:
        """
        构建对话历史
        :return:
        USER: <user_message>
        BOT: <bot_message>
        BOT: <bot_message>
        USER: <user_message>
        BOT: <bot_message>
        """
        messages = ""
        for turn in turns:
            message = ""
            if turn.user_message.text:
                message += f"USER: {turn.user_message.text}\n"
            else:
                message += f"USER: {turn.user_message.object.to_dict()}\n"

            for bot_message in turn.bot_messages:
                if bot_message.text:
                    message += f"BOT: {bot_message.text}\n"
                else:
                    message += f"BOT: {bot_message.object.to_dict()}\n"
            messages += message

        return messages
    
    @staticmethod
    def get_latest_user_message(pending_turn: Turn) -> str:
        """
        获取最新的用户消息
        :param pending_turn:
        :return:
        """
        if pending_turn.user_message.text:
            return pending_turn.user_message.text
        else:
            return str(pending_turn.user_message.object.to_dict())




        
            

            
