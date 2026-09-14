from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependency import init_dialogue_engine
from app.api.routers.chat_router import chat_router
from app.infrastructure.database import init_db_engine, close_db_engine
from app.infrastructure.http_client import client_init, close_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    await client_init()
    init_dialogue_engine()
    init_db_engine()

    yield

    await close_db_engine()
    await close_client()


app = FastAPI(lifespan=lifespan)
app.include_router(chat_router)