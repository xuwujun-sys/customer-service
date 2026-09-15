# 客服后端关键流程图

这些图根据当前 `customer-service` 源码和 YAML Flow 配置整理。

- `.mmd`：Mermaid 源文件，可继续编辑
- `.svg`：矢量图，适合插入 Markdown、Word、PPT
- `.png`：2 倍清晰度位图，适合直接预览和分享

1. `01-system-architecture`：系统组件与外部依赖
2. `02-message-lifecycle`：一条消息从请求到持久化的完整生命周期
3. `03-turn-planner`：Prompt 构造、LLM 输出、Validator 和三轨分流
4. `04-object-message`：订单/商品对象保存、匹配槽位和澄清
5. `05-task-execution`：CommandProcessor、FlowExecutor、ActionRunner
6. `06-slot-collection-sequence`：跨两次 HTTP 请求收集订单号
7. `07-task-interrupt-resume`：用户任务打断、暂停和恢复
8. `08-knowledge-flow`：知识意图、Provider、Chunk 和回答生成
9. `09-configured-business-flows`：当前 YAML 中配置的全部用户业务 Flow

说明：图中明确标出了当前源码中的占位能力，包括真实退款提交、FAQ/RAG 和人工客服集成。

## 配合源码注释的阅读顺序

建议不要按目录字母顺序读，而是按一次真实请求的运行方向读：

1. `main.py`、`app/api/app.py`：进程怎样启动，共享资源怎样初始化。
2. `app/api/routers/chat_router.py`、`app/services/dialogue_service.py`：HTTP 请求怎样变成领域消息，状态怎样加载和保存。
3. `app/domain/dialogue_state.py`、`app/domain/contexts.py`：先理解整个项目真正保存了哪些“对话现场”。
4. `app/engine/dialogue_engine.py`：看一轮消息的总调度，以及文本/对象两条入口。
5. `app/plan/plan.py`、`plan_prompt.jinjia2`、`app/plan/validator.py`：看自然语言怎样变成受限计划。
6. `app/task/command/processor.py`：看 Command 怎样修改 active_task、paused_tasks 和 active_system_task。
7. `app/task/flow/flow_executor.py`、`flow_config/*.yml`：看 step_id 怎样推进，以及 collect 为什么能跨请求暂停和继续。
8. `app/task/action/`：看 Flow 的动作名怎样找到真实 Python 业务实现。
9. `app/knowledge/`、`app/chitchat/`、`app/clarify/`：最后看三条非任务回复路径。
10. `app/repository/`、`app/model/`、`app/infrastructure/`：收尾理解持久化和外部依赖。

每个非空 Python 模块现在都在文件顶部说明了职责、上下游和联动关系；核心 class、
function 说明了创建者、生命周期、输入输出、执行步骤和状态副作用；关键分支旁补了
业务原因。Prompt 使用会在渲染时自动移除的 Jinja 注释，YAML 使用普通配置注释，
不会把学习说明发送给 LLM，也不会改变工作流行为。

## 快速预览

- [系统总体架构](01-system-architecture.svg)
- [消息完整生命周期](02-message-lifecycle.svg)
- [TurnPlanner 规划与校验](03-turn-planner.svg)
- [对象消息与自动补槽](04-object-message.svg)
- [TaskHandler 工作流执行](05-task-execution.svg)
- [跨请求槽位收集时序](06-slot-collection-sequence.svg)
- [任务打断与恢复](07-task-interrupt-resume.svg)
- [Knowledge 知识问答](08-knowledge-flow.svg)
- [当前已配置业务流程](09-configured-business-flows.svg)
