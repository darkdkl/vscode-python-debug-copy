from __future__ import annotations

import dataclasses
import datetime
from typing import Any

import debugpy


@dataclasses.dataclass
class User:
    name: str
    created: datetime.datetime
    roles: list


class Element:
    def __init__(self) -> None:
        self.code = 'E1'
        self.meta = {'code': 5}


class Catalog:
    def __init__(self) -> None:
        self.element = Element()


class Plain:
    pass


def nested_levels(levels: int) -> dict[str, Any]:
    node: dict[str, Any] = {'leaf': True}
    for level in range(levels):
        node = {'level': level, 'items': [node, {'x': list(range(10))}]}
    return node


def main() -> None:
    nested = nested_levels(8)
    big = {'k{}'.format(index): {'payload': 'x' * 200, 'items': list(range(30))} for index in range(2000)}
    user = User('Иван', datetime.datetime(2024, 5, 1, 12, 0), [{'id': 1, 'perms': {'read', 'write'}}])
    keys = {'plain': 1, "it's": 2, 'say "hi"': 3, 'tab\there': 4, 'кириллица': 5, 7: 'int', ('t', 1): 'tuple'}
    catalog = Catalog()
    catalog_dict = {'element': {'code': 7, 'tags': ['a', 'b']}}
    odd = Plain()
    setattr(odd, 'has space', {'x': 1})
    setattr(odd, 'class', 2)
    setattr(odd, "it's", 3)
    error = ValueError('boom', 42)
    debugpy.breakpoint()
    print('done', len(nested), len(big), user.name, len(keys), catalog, catalog_dict, odd, error)


if __name__ == '__main__':
    main()
