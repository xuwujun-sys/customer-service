import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine, create_async_engine
from sqlalchemy import text
from app.config.config import settings

engine: AsyncEngine | None = None
session_factory: async_sessionmaker | None = None

def init_db_engine():
    global engine, session_factory
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def close_db_engine():
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