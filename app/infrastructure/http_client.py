"""应用级异步 HTTP 连接池。

【项目位置】
基础设施层，被 commerce_client 以及 Knowledge API Provider 复用。

【生命周期】
FastAPI lifespan 启动时调用 client_init，关闭时调用 close_client；请求过程中不应
反复创建客户端，否则会失去连接复用并产生连接泄漏。

【联动与修改影响】
修改全局 ``client`` 的生命周期必须同步检查 api/app.py、commerce_client.py 和
knowledge/provider.py。所有调用者都假设请求开始前 client 已完成初始化。
"""

import asyncio
from httpx import AsyncClient
import httpx

client: AsyncClient | None = None

async def client_init():
    """创建全局 AsyncClient。

    输入/返回：无。修改模块级 ``client``。
    ``trust_env=False`` 禁止自动读取系统代理，避免本地电商接口被错误转发。
    """
    global client
    client = httpx.AsyncClient(trust_env=False)

async def close_client():
    """关闭全局连接池；只能在 lifespan 结束阶段调用。"""
    global client
    # 释放 keep-alive 连接与底层 socket；调用后不可再发送业务请求。
    await client.aclose()

if __name__ == '__main__':

    async def test():
        await client_init()
        result = await client.get("http://127.0.0.1:18081/users/u1001/orders")
        print(result.json())
        await close_client()

    asyncio.run(test())
