"""SQLAlchemy 异步数据库引擎和 Session 工厂。

【项目位置】
基础设施层，向 api/dependency.py 提供请求级 AsyncSession。

【生命周期】
FastAPI 启动时初始化 Engine/SessionFactory；每次请求由 get_db 创建 Session；应用
关闭时 dispose Engine。DialogueRepository 不直接创建连接，只使用注入的 Session。

【联动与修改影响】
database_url 来自 Settings；改变 Session 的提交策略会影响 Repository.save_state 的
事务边界。当前模块只建立连接，没有自动建表，表结构需要由外部初始化或迁移保证。
"""

import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine, create_async_engine
from sqlalchemy import text
from app.config.config import settings

engine: AsyncEngine | None = None
session_factory: async_sessionmaker | None = None

def init_db_engine():
    """根据 database_url 创建进程级 Engine 和 Session 工厂。

    ``expire_on_commit=False`` 使提交后的 ORM 对象仍可读取，避免异步环境中因属性
    过期触发隐式 IO。本函数修改两个模块级变量，不返回对象。
    """
    global engine, session_factory
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def close_db_engine():
    """关闭连接池并释放所有数据库连接。"""
    global engine
    await engine.dispose()

async def test():
    init_db_engine()

    async with session_factory() as session:
        result = await session.execute(text('select 1'))
        data = result.fetchall()

        print(data)
    await close_db_engine()


if __name__ == '__main__':
    asyncio.run(test())
