"""TurnPlanner 的 Prompt 输入构造与 LLM 调用实现。

设计原则是只让 LLM 负责“理解并规划”：它看到系统能力菜单与当前状态，
输出结构化 TurnPlan；真正的状态修改和业务调用留给确定性代码完成。
"""

import json
from dataclasses import asdict
from typing import Any
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.dialogue_state import DialogueState
from app.knowledge.intention import KnowledgeIntent
from app.plan.models import TurnPlan
from app.prompts.load_prompt import load_prompt
from app.prompts.build_history import BuildHistory
from app.domain.dialogue_service_domain import MessageType
from app.task.flow.models import FlowsList


def get_user_message(user_message):
    """把当前领域消息转换为 Prompt 可嵌入的字符串。

    文本消息直接使用 text；对象消息将结构化对象转为字符串，保留 id/type 等
    上下文。当前函数对未知消息类型隐式返回 None，调用者依赖 MessageType 只有
    TEXT/OBJECT 两种的领域约束。
    """
    if user_message.type == MessageType.TEXT:
        return user_message.text
    elif user_message.type == MessageType.OBJECT:
        return str(user_message.object.to_dict())

def _build_prompt_inputs(
    state: DialogueState,
    flows: FlowsList,
    knowledge_intents: dict[str, KnowledgeIntent],
) -> dict[str, Any]:
    """把领域对象降维成 ``plan_prompt`` 所需的全部模板变量。

    参数:
        state: 当前用户完整状态，pending_turn 必须已由 Engine 建立；
        flows: 用户 Flow 与系统 Flow 的合集；
        knowledge_intents: 已注册知识能力元数据。
    返回:
        键名与 ``plan_prompt.jinja2`` 占位符一一对应的普通字典。

    本函数只读状态，主要完成历史拼接、dataclass -> dict、dict -> JSON 字符串等
    数据转换。若 Prompt 新增变量，必须在这里同步提供，否则模板渲染时会缺值。
    """

    # pending_turn 是“本轮最新输入”，不能混入已经完成的历史 turns。
    user_message = get_user_message(
        state.pending_turn.user_message
    )

    # 只拼接之前已完成的 Turn，保持“历史”和“当前问题”边界清晰。
    history = BuildHistory.build_history(
        state.current_session().turns
    )

    # Planner 只需知道有哪些 Flow、用途和所需槽位，不需要看到内部 Steps。
    available_flows = [
        {
            key: value
            for key, value in asdict(flow).items()
            if key != "steps"
        }
        for flow in flows.flows
    ]

    # 知识意图同样作为受限菜单提供，避免模型自由发明意图名称。
    knowledge_intent_list = [
        {
            "id": intent.id,
            "description": intent.description,
        }
        for intent in knowledge_intents.values()
    ]

    return {
        # 自然语言上下文：已完成历史 + 本轮最新消息。
        "current_conversation": history,
        "user_message": user_message,

        # 系统能力菜单：允许启动/恢复的 Flow。
        "available_flows_json": json.dumps(
            {"flows": available_flows},
            ensure_ascii=False,
        ),

        # 当前任务让模型理解“ORDER1001”是在回答哪个槽位。
        "active_task_json": json.dumps(
            asdict(state.active_task)
            if state.active_task is not None
            else None,
            ensure_ascii=False,
        ),

        # 暂停任务让模型能够理解“继续刚才的退款”。
        "interrupted_tasks_json": json.dumps(
            [
                asdict(task)
                for task in state.paused_tasks
            ],
            ensure_ascii=False,
        ),

        # 聚焦对象解决“这个商品/这笔订单”的结构化指代问题。
        "focused_object_json": json.dumps(
            asdict(state.focused_object)
            if state.focused_object is not None
            else None,
            ensure_ascii=False,
        ),

        # Knowledge 轨道只能从这里列出的意图中选择。
        "knowledge_intents_json": json.dumps(
            knowledge_intent_list,
            ensure_ascii=False,
        ),
    }


async def _predict_from_prompt_inputs(
    prompt_inputs: dict[str, Any],
) -> TurnPlan:
    """渲染规划 Prompt、调用 LLM、解析 JSON 并建立 ``TurnPlan``。

    参数:
        prompt_inputs: ``_build_prompt_inputs`` 生成的模板变量字典。
    返回:
        可供 Validator 检查的强类型 TurnPlan。

    为什么输出 Command:
        LLM 擅长理解语言但不应直接改变系统状态。Prompt 只允许它从有限命令集
        输出声明式计划；确定性的 CommandProcessor 再检查命令类型并修改状态，
        从而把自然语言的不确定性隔离在规划阶段。

    异常边界:
        模型输出不是合法 JSON、字段缺失或未知命令时，JsonOutputParser 或
        TurnPlan.from_dict 会抛异常。当前代码尚未把此类错误转成澄清回复。
    """

    # 从独立文件读取模板，方便只调整 Prompt 而不改 Python 调度代码。
    prompt_text = load_prompt("plan_prompt")

    # 模板使用 Jinja2，把上面准备的 JSON 和文本嵌入完整指令。
    prompt = PromptTemplate.from_template(
        prompt_text,
        template_format="jinja2",
    )

    from app.infrastructure.llm import llm

    # LCEL 管道：渲染 Prompt -> 调用模型 -> 将模型文本解析成 Python dict。
    chain = (
        prompt
        | llm
        | JsonOutputParser()
    )

    # ainvoke 为异步调用，不阻塞 FastAPI 事件循环等待模型网络响应。
    llm_output: dict = await chain.ainvoke(prompt_inputs)

    # 把无类型 dict 进一步转换为 TurnPlan 和具体 Command 领域对象。
    return TurnPlan.from_dict(llm_output)
