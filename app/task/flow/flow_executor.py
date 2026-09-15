"""YAML 工作流状态机执行器。

执行器反复完成三件事：
1. 根据 active_system_task or active_task 找到当前 Flow/Step；
2. 自动穿过 start、collect、end 等控制步骤，直到产生 ActionCall；
3. 执行 Action、写回 slot/message，再继续推进。

遇到 action_listen 时不会挂起 Python 协程，而是结束本轮执行；当前 step、
slots 和上下文随后由 Repository 保存，下一次 HTTP 请求重新加载后继续。
"""

from dataclasses import asdict

from app.domain.contexts import CollectSystemContext
from app.domain.dialogue_service_domain import BotMessage
from app.domain.dialogue_state import DialogueState
from app.task.action.actionrunner import ActionCall
from app.task.flow.models import FlowsList, Flow
from app.task.action.actionrunner import ActionRunner
from app.task.flow.steps import *

class FlowExecutor():
    """解释执行 YAML Flow，直到遇到 listen 边界或所有任务结束。

    创建者为装配根，生命周期与 Engine 相同；实例不保存游标，真正的运行现场
    全在 DialogueState 的 TaskContext 中。因此 HTTP 请求结束时 Python 调用栈
    消失也没关系，下轮从数据库恢复 step_id/slots 后仍能继续。
    """

    async def run_task(self, state: DialogueState, flows: FlowsList, action_runner: ActionRunner) -> list[BotMessage]:
        """持续推进当前系统/用户任务，直到需要等待下一条用户消息。

        参数:
            state: Command 已应用后的状态，会继续被 Step 和 Action 原地修改；
            flows: 已加载的流程图集合；
            action_runner: 将 ActionCall 分派给具体业务 Action。
        返回:
            本轮所有动作产生的机器人消息，保持产生顺序。

        循环并非跨请求常驻：遇到 action_listen 就 break。暂停效果来自把 step_id、
        slots 持久化，而不是阻塞协程等待用户。
        """
        messages = []
        while True:
            # 自动推进控制步骤，直到遇到一个可执行 Action。
            action_call = self.advance_until_action(state, flows)

            # listen 是流程边界：返回当前回复，等待用户发起下一次 HTTP 请求。
            if action_call.action_name == "action_listen":
                break
            else:
                # 普通 Action 可能同时产生回复和新的槽位值。
                action_res = await action_runner.run(action_call,state)

                # 例如物流 Action 将 tracking_number 等结果写回 active_task。
                # 注意：此方法假定有 active_task 可承接槽位；系统 Flow 的 Action
                # 若产生 slot_updates，需要确认 DialogueState.set_slots 的目标语义。
                state.set_slots(action_res.slot_updates)
                messages.extend(action_res.messages)
        return messages

    def advance_until_action(self, state: DialogueState, flows: FlowsList) -> ActionCall:
        """解释连续控制 Step，直到得到一个应交给 ActionRunner 的调用。

        Start/Collect/End 通常只修改游标或任务状态并返回 None，内部 while 会继续；
        ActionStep 返回 ActionCall，或者没有任务时合成 action_listen。
        """

        while True:
            # 系统提示/收集任务存在时优先，结束后才重新选择用户任务。
            # Python 的 or 体现优先级：只要系统任务存在，就暂时遮住用户任务。
            current_task = state.active_system_task or state.active_task
            if current_task is None:
                # 没有任何任务可推进，统一用 listen 通知外层停止循环。
                return ActionCall(action_name="action_listen")

            # flow_id 定位流程，step_id 定位该流程中的当前节点。
            flow: Flow | None= flows.flow_by_id(current_task.flow_id)
            step: FlowStep | None = flow.step_by_id(current_task.step_id)

            # start/collect/end 常返回 None，循环会继续自动推进；action 返回 ActionCall。
            step_res: ActionCall | None = self._run_step(step, state, flows)

            if step_res is not None:
                return step_res

    def _run_step(self, step, state,flows: FlowsList)->ActionCall | None:
        """依据具体 Step 类型选择解释规则。

        新增 Step 子类时必须同步添加分支，否则 advance_until_action 会原地死循环，
        因为未知 Step 既不返回 ActionCall 也不推进 step_id。
        """
        if isinstance(step, StartFlowStep):
            return self._run_start_step(step, state)
        if isinstance(step, CollectSlotStep):
            return self._run_colletc_step(step, state, flows)
        if isinstance(step, ActionFlowStep):
            return self._run_action_step(step, state)
        if isinstance(step, EndFlowStep):
            return self._run_end_step(state)

    def _run_start_step(self, step: StartFlowStep, state: DialogueState)->ActionCall | None:
        """越过纯入口节点；不产生 ActionCall，外层循环立即处理下一 Step。"""
        # start 只是流程入口，不产生回复，直接移动到 next。
        self._advance_next_step(step, state)

    def _run_colletc_step(self, step: CollectSlotStep, state: DialogueState,flows: FlowsList)->ActionCall | None:
        """处理收集节点：有值则校验并后移，无值则启动临时收集系统 Flow。

        active_task 始终停在当前 collect step。缺值时只是新建优先级更高的
        active_system_task；系统 Flow 最终执行 action_listen 后本轮返回。用户下轮
        给值，SetSlotsCommand 结束系统任务，Executor 重新看到原 collect step，
        此次判断有值才真正推进——这就是“暂停后续跑”的完整机制。
        """

        # 用户此前点击的订单/商品可直接提供 order_number/product_id。
        self._try_to_fill_slot_from_focused_object(step, state)

        # collect Step 本身仍停留在原 step_id，直到这个判断得到有效值。
        if state.active_task.slots.get(step.slot_name, None):
            # 保留原代码的空语句；真正处理逻辑在下面的 validation 分支中。
            pass

            if step.validation:
                # 配置了 validation 时，先执行 YAML 中的条件表达式。
                if self._eval_cond(step.validation.condition, state):
                    self._advance_next_step(step, state)
                    return None
                else:
                    if step.response:
                        # 校验失败先产生提示，本轮不会正常进入下一业务 Step。
                        # failure_response 仍交给统一 ActionRunner，保持回复产生方式一致。
                        return ActionCall(action_name="action_response",
                                          action_kwargs=asdict(step.validation.failure_response))

                    else:
                        # 清掉无效值，让下一次循环重新进入缺槽分支并向用户收集。
                        state.remove_active_task_slots(step.slot_name)
                        return None

            else:
                # 无校验且槽位存在，业务 Flow 可以进入 collect 的 next。
                self._advance_next_step(step, state)
                return None

        else:
            # 缺少槽位：不推进 active_task，而是覆盖一个系统收集任务。
            state.start_new_system_task(CollectSystemContext(
                flow_id="system_collect_information",
                step_id=flows.flow_by_id("system_collect_information").start_step().id,
                slot_name=step.slot_name,
                response=asdict(step.response)
            ))
            return None

        return None

    def _run_action_step(self, step: ActionFlowStep, state: DialogueState)->ActionCall | None:
        """建立 ActionCall，并在执行动作前预先把当前任务游标移向 next。"""
        # 先根据当前 Step 构造调用，再把当前上下文推进到 next。
        action_call = self._build_action_call(step, state)
        self._advance_next_step(step, state)
        return action_call

    def _run_end_step(self,state: DialogueState)->ActionCall | None:
        """根据当前优先级结束系统任务或用户任务，不产生业务动作。"""
        # 系统任务结束只清除 active_system_task，随后自然回到 active_task。
        if state.active_system_task:
            state.end_system_task()
            return None
        # 用户 Flow 结束则清除 active_task，本轮执行器最终返回 listen。
        if state.active_task:
            state.end_user_task()
            return None

    def _select_next_step(self,step: FlowStep,state: DialogueState)->str | None:
        """按 YAML 声明顺序选择第一个成立的后继 Step ID。

        StaticLink 直接命中；ConditionalLink 只有表达式为真才命中；FallbackLink
        是兜底。链接顺序会改变行为，所以条件分支通常应放在 fallback 前面。
        """
        links: List[FlowStepLink] = step.next
        for link in links:
            if isinstance(link, StaticLink):
                return link.target

            if isinstance(link, ConditionalLink):
                condition = link.condition
                if self._eval_cond(condition, state):
                    return link.target

            if isinstance(link, FallbackLink):
                return link.target

    def _eval_cond(self, condition: str, state:DialogueState)->bool:
        """在受限全局环境中计算 YAML 条件表达式。

        表达式只能读取 ``context`` 与 ``slots`` 两个字典，builtins 被清空。配置
        仍属于可执行表达式边界，Flow YAML 必须是受信任的项目文件而非用户输入。
        """
        current_task = state.active_system_task or state.active_task
        data = {
            "context": current_task.to_dict() if current_task else {},
            "slots": state.active_task.slots if state.active_task else {}
        }
        return bool(eval(condition, {"__builtins__": {}}, data))

    def _advance_next_step(self,step: FlowStep,state: DialogueState):
        """选择 next，并写入当前拥有调度权的 TaskContext.step_id。

        若 active_system_task 存在，必须推进它而不是底下的 active_task；否则一条
        系统提示会意外跳过用户业务步骤。
        """
        res = self._select_next_step(step,state)

        # 必须写当前上下文；系统任务运行时不能误改底下的 active_task。
        current_task = state.active_system_task or state.active_task
        current_task.step_id = res

    def _build_action_call(self, step: ActionFlowStep, state: DialogueState) -> ActionCall:
        """把 ActionStep 配置转换成与执行实现解耦的 ``ActionCall``。

        args 可以是静态字典，也可以是 ``context.xxx`` 引用；后者从当前系统/用户
        Context 的 dataclass 字段取真实值。字段名变更要同步修改 YAML。
        """
        action_name = step.action
        args = step.args
        if isinstance(args, str):
            # 例如 args: context.response，要从当前上下文读取实际字典。
            args = asdict(state.active_system_task or state.active_task)[args.split('.')[1]]
        return ActionCall(action_name=action_name, action_kwargs=args)

    def _try_to_fill_slot_from_focused_object(self, step : CollectSlotStep, state:DialogueState)->None:
        """在询问用户前，尝试从 focused_object 自动补当前业务槽位。

        仅允许 order -> order_number、product -> product_id 两组确定映射，避免把
        一个对象 ID 错填到无关字段。写入目标仍是 active_task.slots。
        """
        if state.focused_object is None:
            return None
        if step.slot_name == 'order_number' and state.focused_object.type == 'order':
            state.set_slots({step.slot_name: state.focused_object.id})
        if step.slot_name == 'product_id' and state.focused_object.type == 'product':
            state.set_slots({step.slot_name: state.focused_object.id})





