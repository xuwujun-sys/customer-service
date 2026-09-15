"""电商业务服务（settings.commerce_api_base_url）的统一读取入口。

集中处理三件在各 action 里容易写不一致的事：
1. 成功信封 {"code": 0, "data": {...}} 只把 data 交出去；
2. 失败时服务返回的是 {"detail": "..."} + 非 2xx，不是信封结构，转成 CommerceError；
3. 网络异常、返回非 JSON 都不往外抛裸异常。

CommerceError.message 是中文，可以直接拼进给用户的话术。
"""
from typing import Any

import httpx

import app.infrastructure.http_client as http_client
from app.config.config import settings


class CommerceError(Exception):
    """电商服务返回错误、数据结构不对或不可用。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def get_data(path: str) -> dict[str, Any]:
    """GET 一个接口，返回信封里的 data。失败一律抛 CommerceError。"""
    client = http_client.client
    if client is None:
        raise CommerceError("电商服务客户端未初始化。")

    url = f"{settings.commerce_api_base_url.rstrip('/')}{path}"
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        raise CommerceError("电商服务暂时连不上。") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise CommerceError(f"电商服务返回了无法解析的内容（HTTP {response.status_code}）。") from exc

    if response.status_code != 200:
        raise CommerceError(_detail_text(payload) or f"电商服务返回 HTTP {response.status_code}。",
                            response.status_code)

    if payload.get("code", 0) != 0:
        raise CommerceError(str(payload.get("message") or "电商服务返回失败。"), response.status_code)

    data = payload.get("data")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CommerceError("电商服务返回的 data 不是对象。")
    return data


def _detail_text(payload: Any) -> str:
    """404 的 detail 是字符串；422 的 detail 是 FastAPI 校验错误列表。"""
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):
        return str(detail[0].get("msg") or "")
    return ""
