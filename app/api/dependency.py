"""FastAPI 依赖装配层：把基础设施逐层组合成可调用的应用服务。

依赖链为：``AsyncSession -> DialogueRepository -> DialogueService``，同时把进程级
共享的 ``DialogueEngine`` 注入 ``DialogueService``。路由因此只声明“需要一个
DialogueService”，不必知道数据库连接、状态仓库和引擎是怎样创建的。

生命周期差异非常重要：
* ``DialogueEngine`` 在应用启动时创建一次，多个请求共享；
* ``AsyncSession`` 每次请求创建一个，请求结束立即关闭；
* ``DialogueRepository`` 和 ``DialogueService`` 随请求临时创建。

上游是 ``api.app.lifespan`` 与 ``chat_router``，下游是数据库、Repository 和
Engine。若修改某个依赖的构造参数，需要同步修改本模块的装配函数。
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dialogue_engine import DialogueEngine, build_dialogue_engine
from app.repository.dialogue_state_repository import DialogueRepository
from app.services.dialogue_service import DialogueService


# 模块级变量只保存无会话状态的引擎对象；具体用户状态仍然存放在数据库中。
_dialogue_engine: DialogueEngine | None = None

def init_dialogue_engine() -> None:
    """在应用启动阶段构建一次共享对话引擎。

    输入/返回:
        无输入，也无业务返回值；副作用是写入模块级 ``_dialogue_engine``。

    为什么只创建一次:
        Engine 持有的是 Flow 配置、Handler、Planner 等可复用组件，而不是某位
        用户的 ``DialogueState``，所以没有必要在每个请求中重复读取 YAML 和
        装配整套处理链。
    """
    global _dialogue_engine
    _dialogue_engine = build_dialogue_engine()


def get_engine() -> DialogueEngine:
    """返回 lifespan 启动阶段创建的共享引擎。

    返回值:
        将被 FastAPI 注入 ``get_dialogue_service`` 的 ``DialogueEngine``。

    联动提醒:
        正常运行时 ``api.app.lifespan`` 一定先调用 ``init_dialogue_engine``；类型
        标注写成非空是基于这一生命周期保证。单元测试若直接调用本函数，则要
        先初始化，否则实际可能拿到 ``None``。
    """
    return _dialogue_engine


async def get_db():
    """为单次 HTTP 请求提供一个独立的异步数据库 Session。

    这是带 ``yield`` 的 FastAPI 依赖：yield 前创建 Session，路由处理完成后
    FastAPI 会返回这里退出 ``async with``，从而自动关闭连接。事务提交目前由
    ``DialogueRepository.save_state`` 明确执行；异常时不会误提交未完成状态。
    """
    # 延迟导入可确保真正取用时，lifespan 已经建立好 database.session_factory。
    from app.infrastructure import database

    # Session 只属于当前请求，绝不能保存到共享 Engine 中供其他请求复用。
    async with database.session_factory() as session:
        yield session


async def get_repository(
    db: AsyncSession = Depends(get_db),
) -> DialogueRepository:
    """用当前请求的 Session 创建状态仓库。

    参数:
        db: 由 ``get_db`` 产生、仅在本次请求中有效的异步 Session。
    返回:
        封装 DialogueState 查询和 upsert 的 Repository。
    """
    return DialogueRepository(db)


async def get_dialogue_service(
    engine: DialogueEngine = Depends(get_engine),
    repository: DialogueRepository = Depends(get_repository),
) -> DialogueService:
    """组装路由最终使用的应用服务。

    参数:
        engine: 进程级共享引擎，执行对话编排；
        repository: 请求级仓库，加载并保存当前用户状态。
    返回:
        依赖已完整注入的 ``DialogueService``。

    修改联动:
        ``DialogueService.__init__`` 新增依赖时，本函数也必须同步提供，否则
        FastAPI 在解析依赖时无法构建服务实例。
    """
    return DialogueService(
        dialogue_repository=repository,
        dialogue_engine=engine,
    )
