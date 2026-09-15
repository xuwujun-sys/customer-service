"""应用配置读取模块。

【项目位置】
处于基础配置层，在其他业务模块导入时提供同一份 Settings 单例。

【上游调用者】
main、LLM、数据库和电商 HTTP 模块都会导入 ``settings``。

【下游依赖】
Pydantic Settings 从项目根目录 ``.env`` 和进程环境变量读取配置。

【联动与修改影响】
字段名必须与 `.env`、main.py、database.py、llm.py、commerce_client.py 同步。
``settings = Settings()`` 在导入阶段执行，因此必填项缺失会让应用导入直接失败。
"""

from pathlib import Path

from pydantic_settings import BaseSettings,SettingsConfigDict


# 从当前文件向上两级定位项目根目录，避免启动命令的当前目录影响配置路径。
path = Path(__file__).parents[2] / '.env'

class Settings(BaseSettings):
    """应用全部外部配置的强类型集合。

    由模块末尾创建一次，生命周期与 Python 进程一致。字段没有默认值意味着缺失时
    应尽早失败，而不是运行到某个业务分支后才发现配置不存在。
    """
    # LLM
    llm_api_key: str
    llm_model: str
    llm_base_url: str

    # 数据库
    database_url: str

    # 商城 API
    commerce_api_base_url: str

    # 服务器
    app_host: str
    app_port: int

    # Pydantic 会把字段名映射为不区分大小写的环境变量，例如 llm_api_key。
    model_config = SettingsConfigDict(env_file=path)

# 全局配置单例；下游模块共享读取，不在请求中重复解析 .env。
settings = Settings()

if __name__ == '__main__':
    # 仅供本地排查配置；真实项目不应打印 API Key，后续可移除此测试块。
    print(settings.llm_api_key)
    print(settings.llm_model)
    print(settings.llm_base_url)
