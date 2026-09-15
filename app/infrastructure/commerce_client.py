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
    """统一封装电商服务的 HTTP、业务信封和数据结构错误。

    Action 捕获该异常后可使用中文 message 生成用户话术；status_code 用于区分
    404 与临时服务异常。原始网络异常通过异常链保留供日志排查。
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """保存用户可读错误信息与可选 HTTP 状态码。"""
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def get_data(path: str) -> dict[str, Any]:
    """GET 一个电商接口并只返回成功信封中的 ``data`` 字典。

    参数:
        path: 以 ``/`` 开头的相对 API 路径；基址来自 Settings。
    返回:
        规范化的 data 字典；data 为 null 时返回空字典。
    异常:
        客户端未初始化、网络失败、非 JSON、非 200、业务 code 非零或 data 非对象
        都统一转成 CommerceError。
    """
    client = http_client.client
    if client is None:
        raise CommerceError("电商服务客户端未初始化。")

    # rstrip 防止配置末尾斜杠与 path 开头斜杠拼成双斜杠。
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
    """从 FastAPI 常见错误体中提取最适合展示的一条文本。

    404 的 detail 通常为字符串，422 则是校验错误对象列表；未知形状返回空串，
    调用方再使用 HTTP 状态码生成兜底信息。
    """
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):
        return str(detail[0].get("msg") or "")
    return ""
