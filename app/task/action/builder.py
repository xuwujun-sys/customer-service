"""ActionRunner 装配模块：注册内置动作并自动发现 custom 包中的动作。

由 ``build_dialogue_engine`` 在应用启动时调用。内置 Action 显式注册；自定义 Action
通过包扫描和反射自动注册，因此新增 custom/*.py 子类通常不必再修改装配根。
动作构造函数必须能无参实例化，且 name 必须与 YAML action 字段一致。
"""

import importlib
import inspect
import pkgutil

from app.task.action.buildin.action_response import ActionResponse
from app.task.action.buildin.action_listen import ActionListen
from app.task.action.actionrunner import *
from app.task.action.base import *
from app.task.action.register import *


def register_builtin_actions(action_runner: ActionRunner):
    """显式注册执行器运行边界和通用回复两个框架内置动作。"""
    action_runner.registry.register(ActionResponse())
    action_runner.registry.register(ActionListen())


def register_custom_actions(action_runner: ActionRunner):
    """扫描 ``app.task.action.custom`` 下所有直接定义的 Action 子类并实例化。

    子包被跳过；从别处 import 进模块的类也通过 ``obj.__module__`` 检查排除，防止
    重复注册。任何模块导入错误都会使应用启动失败，便于尽早暴露动作问题。
    """
    # 先导入包以取得 __path__，pkgutil 才能枚举其中的 Python 模块。
    package = importlib.import_module("app.task.action.custom")

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        if is_pkg:
            continue

        # 导入模块会定义其中的 Action 子类，但此阶段还不会执行它们的 run。
        module = importlib.import_module(module_name)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, Action) or obj is Action:
                continue
            if obj.__module__ != module.__name__:
                continue

            # 自定义 Action 生命周期为进程级，故构造函数不应要求请求参数。
            action_runner.registry.register(obj())


def build_action_runner() -> ActionRunner:
    """创建 Registry/Runner，完成全部动作注册后返回可用执行器。"""
    action_runner = ActionRunner(ActionRegistry())
    register_builtin_actions(action_runner)
    register_custom_actions(action_runner)
    return action_runner

# 直接运行时用于人工查看注册结果；FastAPI 导入时不会执行。
if __name__ == '__main__':
    action_runner = build_action_runner()
    print(action_runner)
