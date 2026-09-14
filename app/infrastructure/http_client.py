import asyncio
from httpx import AsyncClient
import httpx

client: AsyncClient | None = None

async def client_init():
    global client
    client = httpx.AsyncClient(trust_env=False)

async def close_client():
    global client
    await client.aclose()

if __name__ == '__main__':

    async def test():
        await client_init()
        result = await client.get("http://127.0.0.1:18081/users/u1001/orders")
        print(result.json())
        await close_client()

    asyncio.run(test())