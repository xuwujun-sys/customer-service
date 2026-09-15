"""Prompt 模板文件读取工具。

Planner 和各 Responder 通过逻辑名称读取同目录的 ``<name>.jinjia2``。文件名是跨模块
契约：修改模板名时必须同步所有 load_prompt 调用，否则只在对应业务分支运行时失败。
"""

from pathlib import Path

def load_prompt(file_name: str) -> str:
    """读取一个 UTF-8 Prompt 模板。

    参数：file_name 为不带扩展名的逻辑名称。
    返回：模板原始文本，后续交给 LangChain PromptTemplate 渲染。
    异常：文件不存在或不可读时直接向上传播，让调用链失败而不是使用错误 Prompt。
    """

    # 相对本模块定位，避免当前工作目录变化导致找不到 Prompt。
    prompt_path = Path(__file__).parent / f"{file_name}.jinjia2"
    return prompt_path.read_text(encoding="utf-8")
