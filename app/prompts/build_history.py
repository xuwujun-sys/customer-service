
"""将结构化 Turn 历史转换为适合放进 Prompt 的纯文本。

【上游】TurnPlanner、KnowledgeResponder、ChitchatResponder、ClarifyResponder 和
ActionResponse 都调用本模块。
【下游】输出文本作为 Jinja2 Prompt 变量交给 LLM。
【联动】Message/BotMessage 增加新消息类型时必须扩展此处，否则历史会丢失信息。
当前没有截断历史，长 Session 会持续增加 Token 消耗。
"""

from app.domain.dialogue_state import Turn


class BuildHistory:
    """无状态历史格式化工具；不需要实例化，方法均为 staticmethod。"""

    @staticmethod
    def build_history(turns: list[Turn]) -> str:
        """按时间顺序构造 USER/BOT 文本历史。

        参数：turns 是当前 Session 中已经提交的轮次，不包含 pending_turn。
        返回：供 Prompt 使用的多行字符串；一轮可包含一条用户消息和多条机器人消息。
        状态修改：无，不会改变 Turn 或 DialogueState。

        输出示例：
            USER: 帮我查物流
            BOT: 请告诉我订单号
        """
        messages = ""
        for turn in turns:
            message = ""

            # 文本消息直接写入；对象消息保留完整字典，确保 ID/type 不丢失。
            if turn.user_message.text:
                message += f"USER: {turn.user_message.text}\n"
            else:
                message += f"USER: {turn.user_message.object.to_dict()}\n"

            # 同一 Turn 可能先确认任务开始，再追问槽位，因此需要遍历所有 BotMessage。
            for bot_message in turn.bot_messages:
                if bot_message.text:
                    message += f"BOT: {bot_message.text}\n"
                else:
                    message += f"BOT: {bot_message.object.to_dict()}\n"
            messages += message

        return messages
    
    @staticmethod
    def get_latest_user_message(pending_turn: Turn) -> str:
        """从 pending_turn 提取本轮用户输入。

        参数：pending_turn 是 Engine 已 begin_turn 但尚未提交的轮次。
        返回：文本原文或对象字典字符串。
        调用者：ActionResponse 的 LLM 改写路径。
        """
        if pending_turn.user_message.text:
            return pending_turn.user_message.text
        else:
            return str(pending_turn.user_message.object.to_dict())




        
            

            
