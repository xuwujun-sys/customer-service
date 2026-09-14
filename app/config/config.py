from pathlib import Path

from pydantic_settings import BaseSettings,SettingsConfigDict


path = Path(__file__).parents[2] / '.env'

class Settings(BaseSettings):
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

    model_config = SettingsConfigDict(env_file=path)

settings = Settings()

if __name__ == '__main__':
    print(settings.llm_api_key)
    print(settings.llm_model)
    print(settings.llm_base_url)