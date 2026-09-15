"""FastAPI 应用对象与进程级资源的生命周期管理。

本模块在项目中的位置
--------------------
``main.py`` 是进程启动入口，而本模块负责创建真正的 :class:`FastAPI` 对象。
Uvicorn 导入 ``main:app`` 时，会间接执行本文件并获得下方的 ``app`` 实例。

上游调用者
----------
* ``main.py`` / Uvicorn：导入并启动 ``app``；
* FastAPI：在应用启动和关闭时回调 ``lifespan``。

下游依赖与联动
--------------
* ``infrastructure.http_client``：创建全局共享的异步 HTTP 客户端；
* ``api.dependency``：创建全局共享的 ``DialogueEngine``；
* ``infrastructure.database``：创建 SQLAlchemy 异步连接池和会话工厂；
* ``api.routers.chat_router``：注册对外 HTTP 路由。

这里决定了资源的创建/销毁顺序。新增需要复用的进程级资源时，应同时补上启动
和关闭逻辑；若只初始化不释放，服务重启或测试时可能产生连接泄漏。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependency import init_dialogue_engine
from app.api.routers.chat_router import chat_router
from app.infrastructure.database import init_db_engine, close_db_engine
from app.infrastructure.http_client import client_init, close_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 FastAPI 从启动到关闭期间共享资源的完整生命周期。

    参数:
        app: 当前 FastAPI 应用实例。此实现暂时不读取它，但保留该参数是
            FastAPI lifespan 协议的要求，也方便未来向 ``app.state`` 挂资源。

    执行流程:
        1. 建立外部 HTTP、对话引擎、数据库三个进程级资源；
        2. 在 ``yield`` 处把控制权交还 FastAPI，让应用开始接收请求；
        3. 应用退出后，从 ``yield`` 后继续执行并释放资源。

    联动提醒:
        ``get_engine`` 和 ``get_db`` 都假设本函数已经执行。若在测试中绕过
        lifespan 直接调用接口依赖，必须由测试代码自行完成初始化。
    """

    # HTTP 客户端必须先初始化，因为知识查询、动作等下游组件会复用它。
    await client_init()

    # Engine 本身不保存用户会话状态，可以在整个进程内只构建一次并安全复用。
    init_dialogue_engine()

    # 创建异步数据库 Engine 及 session_factory；之后每个请求才会各开 Session。
    init_db_engine()

    # 运行边界：yield 之前是 startup，yield 之后是 shutdown。
    yield

    # 先停止数据库连接池，再关闭 HTTP 连接池；两者都属于进程级长寿命资源。
    await close_db_engine()
    await close_client()


# 创建应用时绑定 lifespan，因此部署入口无需再手工调用各项 init/close。
app = FastAPI(lifespan=lifespan)

# 路由只有显式注册后才能被 FastAPI 发现；修改 router 前缀会影响前端请求地址。
app.include_router(chat_router)
