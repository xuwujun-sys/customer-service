"""LLM 结构化输出在 Python 侧对应的本轮规划领域模型。

本模块是 Prompt 与执行代码之间的“数据合同”：Prompt 要求模型输出 task、
knowledge、chitchat 三个字段，``TurnPlan.from_dict`` 再把普通 JSON 递归转换为
这些强类型对象。Engine 和 Validator 后续只依赖这些对象，不直接读模型文本。

上游是 ``plan._predict_from_prompt_inputs`` 的 JSON 解析结果；下游是
``TurnPlanValidator``、``DialogueEngine`` 和 ``CommandProcessor``。修改字段名时
必须同步修改 Prompt、反序列化逻辑及消费该字段的 Handler。
"""

from dataclasses import dataclass, field
from enum import Enum
from app.task.command.models import Command


@dataclass
class TaskTurnPlan:
    """业务任务轨道：保存 LLM 希望按顺序执行的状态命令。

    它存在的原因是把“用户想做什么”转换成有限命令集，例如启动 Flow、补槽、
    取消或恢复任务，而不是让模型直接修改 DialogueState。实例每轮临时创建，
    由 Engine 交给 TaskHandler 消费。
    """
    commands: list[Command] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskTurnPlan":
        """将 ``{"commands": [...]}`` 递归转换成 TaskTurnPlan。

        ``Command.from_dict`` 会依据每项的 command 字段选择具体子类。命令顺序
        会被 TaskHandler 原样执行，因此 Prompt 输出顺序具有业务含义。
        """
        # 每个普通字典会继续映射为 Start/Set/Cancel/Resume 具体 Command。
        return cls(commands=[Command.from_dict(command) for command in data["commands"]])


@dataclass
class KnowledgeTurnPlan:
    """知识问答轨道：声明本轮需要检索的一个或多个受限知识意图。

    intents 中保存的是 ``knowledge.intention.KNOWLEDGE_INTENTS`` 的键，而不是
    自由文本。KnowledgeHandler 会用这些键选择 Provider 并取得参考资料。
    """
    intents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeTurnPlan":
        """从 LLM JSON 取出意图 ID 列表；本阶段尚不验证 ID 是否注册。"""
        return cls(intents=data["intents"])


@dataclass
class ChitchatTurnPlan:
    """闲聊轨道的标记对象。

    闲聊没有命令或检索意图，所以无需字段；实例存在本身就表示选择了该轨道。
    """
    pass


@dataclass(slots=True)
class TurnPlan:
    """一次用户文本经过规划后得到的三轨互斥结果。

    由 TurnPlanner 创建，仅在当前轮使用。正常计划应且只能有一个非 None 字段；
    这个约束不靠 LLM 自觉，而由 ``TurnPlanValidator`` 再次检查。
    """
    task: TaskTurnPlan | None = None
    knowledge: KnowledgeTurnPlan | None = None
    chitchat: ChitchatTurnPlan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "TurnPlan":
        """把 JsonOutputParser 生成的 dict 转为嵌套领域对象。

        输入中的键名直接受 ``plan_prompt.jinja2`` 输出格式约束。该方法负责类型
        转换而非容错校验：缺少必要子字段或未知 command 可能在这里直接抛异常，
        尚未进入 Validator。这是后续增强模型输出防御时需要关注的边界。
        """
        # null 保持为 None；非 null 字段转换成对应的强类型子计划。
        return cls(
            task=TaskTurnPlan.from_dict(data["task"]) if data.get("task") is not None else None,
            knowledge=KnowledgeTurnPlan.from_dict(data["knowledge"]) if data.get("knowledge") is not None else None,
            chitchat=ChitchatTurnPlan() if data.get("chitchat") is not None else None,
        )



class ClarifyReason(str, Enum):
    """计划无法安全执行时的标准原因码。

    Validator 和对象消息分支产生该枚举，ClarifyResponder 将它转换为用户可读
    追问。新增原因必须同步补 ``ClarifyResponder.build_clarify_message`` 分支。
    """
    MISSING_TRACK = "missing_track"
    MULTIPLE_TRACKS = "multiple_tracks"
    MISSING_TASK_COMMANDS = "missing_task_commands"
    MISSING_KNOWLEDGE_INTENT = "missing_knowledge_intent"
    MISSING_FOCUSED_OBJECT = "missing_focused_object"
    OBJECT_REQUIRES_INTENT = "object_requires_intent"


@dataclass
class TurnPlanValidationResult:
    """Validator 的显式结果对象。

    ``valid=True`` 时 Engine 可以执行计划；失败时 ``reason`` 告诉澄清模块为何
    不能执行。使用返回对象而非抛异常，是因为信息不足属于正常对话分支。
    """
    valid: bool
    reason: ClarifyReason | None = None
