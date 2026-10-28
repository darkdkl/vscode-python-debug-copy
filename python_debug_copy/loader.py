from __future__ import annotations

import sys
import types


def load_modules(sources: list[list[str]]) -> dict[str, types.ModuleType]:
    previous = {name: sys.modules.get(name) for name, _ in sources}
    modules: dict[str, types.ModuleType] = {}
    try:
        for name, source in sources:
            module = types.ModuleType(name)
            sys.modules[name] = module
            exec(compile(source, name, 'exec'), module.__dict__)
            modules[name] = module
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return modules
