"""客服后端进程启动入口。

【项目位置】
这是整个应用最外层的可执行文件，只负责启动 ASGI 服务器，不承载业务逻辑。

【上游调用者】
开发者通过 ``python main.py`` 或 ``uv run python main.py`` 执行本文件。

【下游依赖】
读取 ``app.config.config.settings`` 中的监听地址，然后让 Uvicorn 导入
``app.api.app:app``。FastAPI 应用、数据库、LLM 和业务组件都在后续模块初始化。

【联动与修改影响】
- ``app`` 字符串必须和 ``app/api/app.py`` 中的 FastAPI 实例位置一致；
- host/port 字段必须和 ``Settings``、`.env` 同步；
- 修改 reload 策略会影响开发/生产启动行为，但不影响对话业务代码。
"""

import uvicorn

from app.config.config import settings


def main():
    """启动 Uvicorn 并加载 FastAPI 应用。

    参数：无，所有启动参数来自全局 ``settings``。
    返回：无；该调用会占用当前进程运行 Web 服务，直到服务退出。
    调用链：main -> uvicorn -> app.api.app -> lifespan -> 各基础设施初始化。
    状态修改：本函数不修改对话状态，只创建服务进程。
    """

    # 使用字符串导入路径，配合 reload 时 Uvicorn 可以重新导入应用模块。
    uvicorn.run(
        app='app.api.app:app',
        host=settings.app_host,
        port=settings.app_port,
        reload=True
    )

# 只有直接执行本文件时才启动；被测试或其他模块 import 时不会自动运行服务器。
if __name__ == "__main__":
    main()
