"""对话引擎：整个客服系统的一轮消息总调度器。

本模块处在应用服务与各业务轨道之间，真实调用链是：
``DialogueService -> DialogueEngine -> Planner/Validator -> Handler``。

主要职责
--------
1. 恢复或新建 Session，并开启本轮 pending Turn；
2. 区分自然语言消息和商品/订单对象消息；
3. 文本消息先交给 TurnPlanner 生成结构化计划，再由 Validator 做确定性校验；
4. 将合法计划路由到 Task、Knowledge、Chitchat 三条互斥轨道；
5. 把不完整/冲突计划路由到 ClarifyResponder；
6. 汇总回复并提交 Turn，使它成为下一轮可见的历史。

职责边界
--------
Engine 只决定“本轮交给谁”和“一轮状态何时提交”。它不执行退款、不查询商品、
也不亲自推进 Flow：这些分别属于 Action、KnowledgeProvider 和 TaskHandler。

关键联动
--------
* Planner 输出的数据结构必须与 ``plan.models`` 和 Prompt 模板一致；
* Task 命令必须与 ``CommandProcessor`` 支持的 command 名一致；
* 对象消息的 ``type/id`` 必须与 Flow 中等待的槽位名一致；
* ``pending_turn`` 只有在本模块末尾提交后，才会进入下一轮 Prompt 历史。

修改此模块会影响全部消息入口，尤其要留意暂停任务和对象补槽的状态变化。
"""

from pathlib import Path

from app.chitchat.handler import ChitchatHandler
from app.chitchat.responder import ChitchatResponder
from app.clarify.clarify_respond import ClarifyResponder
from app.domain.contexts import CollectSystemContext
from app.domain.dialogue_service_domain import Message, ProcessResult, MessageType, BotMessage
from app.domain.dialogue_state import DialogueState, FocusedObject
from app.knowledge.handler import KnowledgeHandler
from app.knowledge.intention import KNOWLEDGE_INTENTS
from app.knowledge.provider import ProductAPIProvider, OrderAPIProvider, FAQProvider, RAGProvider
from app.knowledge.register import KnowledgeProviderRegistry
from app.knowledge.responder import KnowledgeResponder
from app.plan.models import ClarifyReason
from app.plan.planner import TurnPlanner
from app.plan.validator import TurnPlanValidator
from app.task.action.builder import build_action_runner
from app.task.command.models import Command, SetSlotsCommand
from app.task.command.processor import CommandProcessor
from app.task.flow.flow_executor import FlowExecutor
from app.task.flow.loader import FlowLoader
from app.task.flow.models import FlowsList
from app.task.flow.steps import CollectSlotStep
from app.task.handler import TaskHandler
import time

_PROJECT_ROOT = Path(__file__).parents[2]
_FLOW_CONFIG_DIR = _PROJECT_ROOT / "flow_config"
_FLOW_CONFIG_FILES = (
    "user_flows.yml",
    "system_flows.yml",
)


class DialogueEngine:
    """协调规划器、校验器、各 Handler 与一轮对话状态生命周期。

    为什么存在:
        各 Handler 只理解自己的轨道。如果由 API 直接调用它们，就没有统一位置
        管理 Session、Turn、澄清与轨道互斥。本类提供这一层总编排。

    创建者与生命周期:
        ``build_dialogue_engine`` 在 FastAPI lifespan 启动阶段创建一次，随后由
        所有请求共享。它不保存某个用户的 DialogueState，所以不会串用户数据。

    协作对象:
        TurnPlanner 负责“理解”；Validator 负责“把关”；Task/Knowledge/Chitchat
        Handler 负责“执行”；ClarifyResponder 负责无法安全执行时的追问。
    """

    def __init__(
            self,
            turn_planner: TurnPlanner,
            task_handler: TaskHandler,
            knowledge_handler: KnowledgeHandler,
            chitchat_handler: ChitchatHandler,
            clarify_responder: ClarifyResponder,
            turn_plan_validator: TurnPlanValidator,
    ) -> None:
        """接收装配根创建好的全部协作者，不在运行中临时创建组件。

        参数分别对应规划、任务执行、知识问答、闲聊、澄清和计划校验。集中注入
        便于单元测试替换其中任意组件，也避免每轮消息重复加载 Flow/Prompt。
        """
        self.turn_planner = turn_planner
        self.task_handler = task_handler
        self.knowledge_handler = knowledge_handler
        self.chitchat_handler = chitchat_handler
        self.clarify_responder = clarify_responder
        self.turn_plan_validator = turn_plan_validator


    async def process_message(
            self,
            state: DialogueState,
            user_message: Message,
    ) -> ProcessResult:
        """处理一条用户消息，并完成本轮状态的原子式生命周期。

        参数:
            state: Repository 从数据库恢复的用户状态。本方法会原地修改它；
            user_message: Router 转换出的领域消息，包含文本或业务对象。
        返回:
            包含 sender_id、原 message_id 和本轮所有机器人回复的 ProcessResult。

        执行流程:
            准备 Session -> 创建 pending Turn -> 按消息类型处理 -> 收集 BotMessage
            -> 提交 pending Turn -> 返回结果。

        重要设计:
            处理期间先写 ``pending_turn`` 而不是直接写历史。只有所有 Handler 正常
            返回才调用 ``commit_pending_turn``；异常会向上抛给 Service，且 Service
            不保存这份半完成状态。
        """

        # 确保用户有一个可用 Session；超过一小时则开启新 Session。
        self._prepare_session(state)

        # 当前消息先进入 pending_turn，处理完成后才会写入正式历史。
        self._begin_turn(state, user_message)

        # 文本需要 LLM 理解意图；对象消息已有明确的商品/订单 ID，可直接处理。
        if user_message.type is MessageType.TEXT:
            messages = await self._handle_text_message(
                state=state,
            )
        else:
            # 记住用户当前选中的对象，后续“这个商品/这笔订单”都可引用它。
            # 此状态不仅服务当前对象补槽，也会进入后续 Planner Prompt 的上下文。
            state.set_focused_object(
                FocusedObject.from_dict(user_message.object.to_dict())
            )
            messages = await self._handle_object_message(
                message=user_message,
                state=state,
            )

        # 将本轮产生的所有机器人消息补入临时 Turn。
        state.pending_turn.bot_messages.extend(messages)

        # 本轮处理成功完成：pending_turn 正式进入当前 Session 的 turns。
        state.commit_pending_turn()

        # 保留请求 message_id，方便前端把响应和请求对应起来。
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

    def _prepare_session(self, state: DialogueState) -> None:
        """保证本轮开始前存在一个有效 Session。

        参数:
            state: 将被直接修改的用户对话状态。
        返回:
            无；可能创建 Session、关闭旧 Session、清空运行态或刷新活动时间。

        规则:
            无 Session 时新建；距离上次活动超过一小时则关闭旧会话并清除任务
            运行现场；否则沿用原会话。历史 Session 仍会保留，只是不再续接任务。
        """
        session = state.current_session()
        now = time.time()

        # 新用户或尚未建立会话的用户，直接创建第一个 Session。
        if session is None:
            state.start_session()
            return

        # 一小时无活动视为新会话：保留历史 Session，但清空任务运行现场。
        if now - session.last_activity_at > 60 * 60:
            state.close_current_session()
            # active_task、paused_tasks、active_system_task 属于会话现场，不能跨超时续跑。
            state.reset_runtime_state_for_new_session()
            state.start_session()
        else:
            # 仍在当前会话中，只刷新最后活动时间。
            session.last_activity_at = now

    def _begin_turn(self, state, user_message):
        """把最新用户消息放入尚未提交的临时 Turn。

        ``DialogueState.begin_turn`` 会改写 ``state.pending_turn``。后续 Planner 读取
        当前用户话语也依赖这个字段，而本轮 BotMessage 会在 process_message 尾部
        补入同一个 Turn，因此调用顺序不能随意调整。
        """
        state.begin_turn(user_message)

    async def _handle_text_message(
            self,
            state: DialogueState,
    ) -> list[BotMessage]:
        """理解文本、校验结构化计划，并路由到唯一处理轨道。

        输入:
            state: 已包含当前 pending_turn 的对话状态。
        返回:
            当前轨道产生的一条或多条 BotMessage。

        数据流:
            DialogueState + Flow/知识能力清单 -> TurnPlanner -> TurnPlan
            -> TurnPlanValidator -> Task/Knowledge/Chitchat/Clarify。

        状态变化:
            TaskHandler 可能创建/推进/暂停/结束任务；知识与闲聊分支会先暂停正在
            运行的业务任务，确保用户的临时插话不会被当成业务槽位继续执行。
        """

        # Planner 根据历史、任务状态、聚焦对象和能力清单，让 LLM 生成 TurnPlan。
        turn_plan = await self.turn_planner.predict(
            state,
            self.task_handler.flows,
            self.knowledge_handler.knowledge_intents,
        )

        # LLM 输出可解析不等于业务上可执行，因此必须再做确定性校验。
        validation = self.turn_plan_validator.validate(
            turn_plan,
            state=state,
            knowledge_intents=self.knowledge_handler.knowledge_intents,
        )

        if not validation.valid:
            # 缺少轨道、同时命中多轨道、缺少对象等情况，都通过追问用户解决。
            # 此时不运行任何任务命令，避免拿不确定的 LLM 输出直接修改业务状态。
            return await self.clarify_responder.respond(state=state,
                                                        reason=validation.reason)

        if turn_plan.task is not None:
            # Task 轨道：执行 start_flow/set_slots/cancel_flow/resume_flow 等命令。
            return await self.task_handler.handle(
                commands=turn_plan.task.commands,
                state=state,
            )

        elif turn_plan.knowledge is not None:
            # 用户临时咨询知识时，先保存当前业务任务进度，避免意外继续推进。
            if state.active_task:
                # pause_active_task 保存完整 TaskContext（flow_id、step_id、slots），
                # 后续 resume_flow 命令才能从保存的现场继续，而不是重新猜测进度。
                state.pause_active_task()

            # KnowledgeHandler 负责选 Provider、取资料、基于资料生成答案。
            return await self.knowledge_handler.handle(
                state=state,
                intents=turn_plan.knowledge.intents,
            )

        # 剩余的合法轨道是 chitchat；闲聊同样不应被误当成当前任务的槽位。
        if state.active_task:
            # 闲聊同样属于“插话”；暂停只改变任务存放位置，不会执行取消或清空槽位。
            state.pause_active_task()

        return await self.chitchat_handler.handle(state=state)


    async def _handle_object_message(
            self,
            message: Message,
            state: DialogueState,
    ) -> list[BotMessage]:
        """尝试把商品/订单卡片转换为当前任务需要的槽位值。

        参数:
            message: OBJECT 类型消息，其中 object.id 是候选业务 ID；
            state: 当前用户状态，用于判断正在等待哪个槽位；
        返回:
            TaskHandler 继续运行后产生的消息；无法映射时返回澄清消息。

        为什么不经过 Planner:
            对象的类型和 ID 已经是结构化数据。如果当前恰好等待 order_number 或
            product_id，可以用确定性规则生成 SetSlotsCommand，避免 LLM 改写 ID。

        “补槽后继续”的关键:
            SetSlotsCommand 并不是替换原 Task。CommandProcessor 只把 ID 写进现有
            ``active_task.slots``；随后同一次 TaskHandler.handle 会调用
            FlowExecutor，从 ``active_task.step_id`` 保存的位置继续执行原 Flow。
        """

        # 对象消息不经过 LLM Planner，只尝试映射成确定性的 set_slots 命令。
        command = self._object_slot_command(
            message=message,
            state=state,
            flows=self.task_handler.flows,
        )

        if command is None:
            # 收到了对象，但当前没有等待对应 ID，不能擅自猜测用户要查什么。
            return await self.clarify_responder.respond(state=state,
                                                  reason=ClarifyReason.OBJECT_REQUIRES_INTENT)

        # 例如 order 对象补为 order_number 后，继续执行原有业务 Flow。
        return await self.task_handler.handle(
            commands=[command],
            state=state,
        )

    def _object_slot_command(
            self,
            message: Message,
            state: DialogueState,
            flows: FlowsList,
    ) -> Command | None:
        """根据对象类型和当前等待槽位构造确定性 ``SetSlotsCommand``。

        返回:
            order/product 与等待槽位匹配时返回命令，否则返回 ``None``。
        状态影响:
            本函数只判断和构造命令，不写槽位；真正状态修改发生在
            ``CommandProcessor`` 执行该命令时。
        """
        message_object = message.object

        # API 层保留客户端原始字符串；这里统一大小写和首尾空格再做业务匹配。
        object_type = message_object.type.strip().lower()

        # 优先从 CollectSystemContext 读取等待项，否则检查 active_task 当前 Step。
        collect_slot_name = self._current_collect_slot_name(
            state=state,
            flows=flows,
        )

        if object_type == "order" and collect_slot_name == "order_number":
            # 订单卡片的 id 就是业务流程需要的 order_number。
            return SetSlotsCommand(
                command="set_slots",
                slots={"order_number": message_object.id},
            )

        if object_type == "product" and collect_slot_name == "product_id":
            # 商品卡片的 id 就是业务流程需要的 product_id。
            return SetSlotsCommand(
                command="set_slots",
                slots={"product_id": message_object.id},
            )

        return None

    @staticmethod
    def _current_collect_slot_name(
            state: DialogueState,
            flows: FlowsList,
    ) -> str | None:
        """从系统收集任务或当前 Flow Step 中找出正在等待的槽位。

        查找优先级:
            1. ``active_system_task``：缺槽时由 FlowExecutor 启动的专用收集流程；
            2. ``active_task.step_id``：业务 Flow 自身正停在 CollectSlotStep；
            3. 两者都没有则返回 None。

        此方法只读状态。它与 ``FlowExecutor`` 创建 CollectSystemContext 的逻辑、
        YAML 中 ``collect`` Step 的 ``slot_name`` 字段存在直接联动。
        """

        # 缺槽位时 FlowExecutor 会创建专门的 CollectSystemContext。
        if isinstance(state.active_system_task, CollectSystemContext):
            return state.active_system_task.slot_name or None

        # 没有系统收集任务时，再检查用户任务是否正停在 collect Step。
        active_task = state.active_task
        if active_task is None:
            return None

        # flow_id/step_id 都来自持久化 TaskContext，必须能在当前 YAML 配置中找到。
        current_flow = flows.flow_by_id(active_task.flow_id)

        # 注意：Flow 当前公开方法名是 step_by_id；这里使用 get_step_by_id 存在接口
        # 不一致风险。本文档化阶段保留原逻辑，修复时需同时补对象消息场景测试。
        current_step = current_flow.get_step_by_id(active_task.step_id)

        if not isinstance(current_step, CollectSlotStep):
            return None

        return current_step.slot_name



def build_dialogue_engine() -> DialogueEngine:
    """在应用启动时装配完整的、可跨请求复用的 ``DialogueEngine``。

    输入:
        无。Flow 配置路径由项目根目录和固定文件名决定。
    返回:
        Planner、各 Handler、Validator 均已注入的 Engine。

    执行流程:
        加载用户/系统 Flow YAML -> 构建 ActionRunner -> 注册 KnowledgeProvider
        -> 创建所有 Handler -> 注入 DialogueEngine。

    修改联动:
        新增 Flow 配置文件、KnowledgeProvider 或 Handler 时，通常都要在这里注册；
        仅定义类而未加入装配根，运行时不会自动生效。
    """

    # 用户业务 Flow 与系统辅助 Flow 最终合并成同一份 FlowsList。
    flow_paths = [
        _FLOW_CONFIG_DIR / filename
        for filename in _FLOW_CONFIG_FILES
    ]
    # 启动时一次性解析并校验；若 YAML 非法，应用应尽早启动失败而非请求中失败。
    flows = FlowLoader().load_many(flow_paths)

    # 这里是项目的“装配根”：集中声明各模块依赖，业务代码无需自己创建组件。
    return DialogueEngine(
        turn_planner=TurnPlanner(),
        task_handler=TaskHandler(
            flows=flows,
            command_processor=CommandProcessor(),
            flow_executor=FlowExecutor(),
            action_runner=build_action_runner(),
        ),
        knowledge_handler=KnowledgeHandler(
            knowledge_intents=KNOWLEDGE_INTENTS,
            knowledge_responder=KnowledgeResponder(),
            provider_registry=KnowledgeProviderRegistry(
                [
                    ProductAPIProvider(),
                    OrderAPIProvider(),
                    FAQProvider(),
                    RAGProvider(),
                ]
            ),
        ),
        chitchat_handler=ChitchatHandler(
            responder=ChitchatResponder(),
        ),
        clarify_responder=ClarifyResponder(),
        turn_plan_validator=TurnPlanValidator(),
    )
