"""全局大语言模型客户端。

【项目位置】
基础设施层的 LLM 适配器。Planner、KnowledgeResponder、ChitchatResponder、
ClarifyResponder 和 ActionResponse 都复用这里创建的 LangChain Runnable。

【创建与生命周期】
模块首次导入时创建 ``llm``，随后在整个进程内共享；真正网络请求发生在 invoke/
ainvoke 时。模块不保存用户状态，对话上下文均由调用者通过 Prompt 显式传入。

【联动与修改影响】
模型名、地址和密钥来自 Settings；温度会影响 TurnPlan JSON 的稳定性。替换模型时
要同时验证 JsonOutputParser、中文生成效果和 OpenAI-compatible 接口兼容性。
"""

from langchain.chat_models import init_chat_model

from app.config.config import settings

# temperature=0 让规划结果尽量稳定，但仍不能替代 Validator 和异常处理。
llm = init_chat_model(
    model=settings.llm_model,
    model_provider='openai',
    api_key=settings.llm_api_key,
    temperature=0,
    base_url=settings.llm_base_url
)

if __name__ == "__main__":
    print(llm.invoke("hello").content)
