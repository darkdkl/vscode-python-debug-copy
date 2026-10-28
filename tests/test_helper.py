from __future__ import annotations

import ast
import base64
import builtins
import collections
import dataclasses
import datetime
import decimal
import enum
import json
import pathlib
import sys
import unittest
import uuid
from typing import Any

from python_debug_copy import helper, loader
from python_debug_copy.constants import ModeEnum, OptionEnum, TemplateEnum

STORAGE_KEY = '__python_debug_copy_test__'
PACKAGE_DIRECTORY = pathlib.Path(helper.__file__).parent
check = unittest.TestCase()


def serialize(value: Any, **options: Any) -> str:
    payload_length = int(helper.run(value, json.dumps(options), STORAGE_KEY))
    payload = getattr(builtins, STORAGE_KEY)
    delattr(builtins, STORAGE_KEY)
    check.assertEqual(len(payload), payload_length)
    return base64.b64decode(payload).decode('utf-8')


def fake_type(module: str, name: str, **members: Any) -> type:
    return type(name, (), {'__module__': module, **members})


def nested_levels(levels: int) -> dict[str, Any]:
    node: dict[str, Any] = {'leaf': True}
    for level in range(levels):
        node = {'level': level, 'items': [node, {'x': list(range(100))}]}
    return node


class Color(enum.Enum):
    RED = 'red'


@dataclasses.dataclass
class Point:
    x: int
    y: int
    tags: list = dataclasses.field(default_factory=list)


class Plain:
    def __init__(self) -> None:
        self.name = 'plain'
        self._private = 1
        self.child = None


class Slotted:
    __slots__ = ('a', '__b')

    def __init__(self) -> None:
        self.a = 1
        self.__b = 2


Pair = collections.namedtuple('Pair', 'a b')


def test_deep_nesting_is_not_truncated() -> None:
    data = nested_levels(30)
    check.assertEqual(json.loads(serialize(data)), data)


def test_large_collection() -> None:
    data = {'k{}'.format(index): {'v': list(range(50))} for index in range(500)}
    check.assertEqual(json.loads(serialize(data)), data)


def test_unicode() -> None:
    data = {'привет': 'мир ✓'}
    check.assertIn('привет', serialize(data))
    check.assertIn('\\u043f', serialize(data, ensureAscii=True))


def test_special_types_in_json() -> None:
    data = {
        'dt': datetime.datetime(2024, 1, 2, 3, 4, 5),
        'd': datetime.date(2024, 1, 2),
        'td': datetime.timedelta(seconds=90),
        'dec': decimal.Decimal('1.10'),
        'u': uuid.UUID(int=1),
        'set': {3, 1, 2},
        'tuple': (1, 2),
        'bytes': b'abc',
        'badbytes': b'\xff',
        'enum': Color.RED,
        'nan': float('nan'),
        1: 'int key',
        (1, 2): 'tuple key',
    }
    check.assertEqual(json.loads(serialize(data)), {
        'dt': '2024-01-02T03:04:05',
        'd': '2024-01-02',
        'td': '0:01:30',
        'dec': '1.10',
        'u': '00000000-0000-0000-0000-000000000001',
        'set': [1, 2, 3],
        'tuple': [1, 2],
        'bytes': 'abc',
        'badbytes': "b'\\xff'",
        'enum': 'red',
        'nan': None,
        '1': 'int key',
        '(1, 2)': 'tuple key',
    })


def test_objects_in_json() -> None:
    check.assertEqual(json.loads(serialize(Point(1, 2, [Plain()]))), {
        'x': 1,
        'y': 2,
        'tags': [{'name': 'plain', '_private': 1, 'child': None}],
    })
    check.assertEqual(json.loads(serialize(Plain(), skipPrivateAttributes=True, includeTypeName=True)), {
        '__type__': Plain.__module__ + '.Plain',
        'name': 'plain',
        'child': None,
    })
    check.assertEqual(json.loads(serialize(Slotted())), {'a': 1, '_Slotted__b': 2})
    check.assertEqual(json.loads(serialize(Pair(1, [2]))), {'a': 1, 'b': [2]})


def test_cycles_and_shared_references() -> None:
    node: dict[str, Any] = {'name': 'node'}
    node['self'] = node
    check.assertEqual(json.loads(serialize(node))['self'], '<circular reference: dict>')
    shared = [1]
    check.assertEqual(json.loads(serialize({'a': shared, 'b': shared})), {'a': [1], 'b': [1]})


def test_max_depth() -> None:
    check.assertIn('max depth', serialize(nested_levels(5), maxDepth=3))


def test_indent_and_sort() -> None:
    check.assertEqual(serialize({'b': 1, 'a': 2}, indent=0, sortKeys=True), '{"a":2,"b":1}')
    check.assertEqual(json.loads(serialize({'b': 1, 2: 2}, sortKeys=True)), {'b': 1, '2': 2})


def test_scalars_and_str_subclass() -> None:
    class Text(str):
        pass

    check.assertEqual(serialize('text'), '"text"')
    check.assertEqual(serialize(None), 'null')
    check.assertEqual(serialize(Text('x')), '"x"')


def test_broken_repr() -> None:
    class BrokenRepr:
        def __init__(self) -> None:
            self.ok = 1

        def __repr__(self) -> str:
            raise RuntimeError('boom')

    check.assertEqual(json.loads(serialize(BrokenRepr())), {'ok': 1})


def test_exceptions_in_json() -> None:
    class AppError(Exception):
        def __init__(self, message: str, code: dict[str, int]) -> None:
            super().__init__(message)
            self.code = code

    check.assertEqual(json.loads(serialize(ValueError('boom', 42))), {'type': 'ValueError', 'args': ['boom', 42]})
    check.assertEqual(json.loads(serialize(AppError('bad', {'http': 500}))), {
        'type': AppError.__module__ + '.test_exceptions_in_json.<locals>.AppError',
        'args': ['bad'],
        'code': {'http': 500},
    })


def test_real_key_keeps_its_name() -> None:
    for data in ({'red': 'str', Color.RED: 'enum'}, {Color.RED: 'enum', 'red': 'str'}):
        result = json.loads(serialize(data))
        check.assertEqual(result, {'red': 'str', "<Color.RED: 'red'>": 'enum'})
        check.assertEqual(list(result.values()), list(data.values()))


def test_keys_equal_after_conversion_are_kept() -> None:
    result = json.loads(serialize({1: 'int', Color.RED: 'enum', '1': 'str'}))
    check.assertEqual(sorted(result.values()), ['enum', 'int', 'str'])
    check.assertEqual(result['red'], 'enum')
    result = json.loads(serialize({Color.RED: 'enum', 'red': 'str', "<Color.RED: 'red'>": 'repr'}))
    check.assertEqual(sorted(result.values()), ['enum', 'repr', 'str'])
    check.assertEqual(result['red'], 'str')


def test_json_keys() -> None:
    check.assertEqual(serialize({True: 1, None: 2, 1.5: 3, float('nan'): 4, -7: 5}, indent=0), '{"true":1,"null":2,"1.5":3,"NaN":4,"-7":5}')


def test_pandas_like_values() -> None:
    values = {
        'nat': fake_type('pandas._libs.tslibs.nattype', 'NaTType')(),
        'na': fake_type('pandas._libs.missing', 'NAType')(),
        'frame': fake_type('pandas.core.frame', 'DataFrame', to_dict=lambda frame, orient='dict': {'orient': orient})(),
        'series': fake_type('pandas.core.series', 'Series', to_dict=lambda series: {'x': 1})(),
        'index': fake_type('pandas.core.indexes.base', 'Index', __iter__=lambda index: iter([1, 2]))(),
    }
    check.assertEqual(json.loads(serialize(values, dataFrameOrient='split')), {
        'nat': None,
        'na': None,
        'frame': {'orient': 'split'},
        'series': {'x': 1},
        'index': [1, 2],
    })


def test_numpy_like_values() -> None:
    array = fake_type('numpy', 'ndarray', tolist=lambda array: [[1, 2], [3, float('nan')]])()
    scalar = fake_type('numpy', 'int64', item=lambda scalar: 7)()
    check.assertEqual(json.loads(serialize({'array': array, 'scalar': scalar})), {'array': [[1, 2], [3, None]], 'scalar': 7})


def test_python_roundtrip_literal() -> None:
    data = nested_levels(20)
    check.assertEqual(ast.literal_eval(serialize(data, mode='python')), data)


def test_python_keeps_python_types() -> None:
    result = serialize({'t': (1, 2), 's': {1, 2}, 'b': b'x', 1: None, (1, 2): 'tk', 'f': float('inf')}, mode='python')
    check.assertIn('(1, 2)', result)
    check.assertIn("b'x'", result)
    check.assertIn('inf', result)


def test_python_datetime_repr() -> None:
    check.assertIn('datetime.datetime(2024, 1, 2, 0, 0)', serialize({'dt': datetime.datetime(2024, 1, 2)}, mode='python'))


def test_python_objects_become_dicts() -> None:
    check.assertEqual(ast.literal_eval(serialize(Point(1, 2), mode='python')), {'x': 1, 'y': 2, 'tags': []})


def test_python_exceptions() -> None:
    check.assertEqual(serialize({'error': ValueError('boom', 42)}, mode='python'), "{'error': ValueError('boom', 42)}")


def test_python_enum_key_equal_to_another_key() -> None:
    class Number(enum.Enum):
        ONE = 1

    result = serialize({1: 'int', Number.ONE: 'enum'}, mode='python')
    check.assertEqual(ast.literal_eval(result), {1: 'int', '<Number.ONE: 1>': 'enum'})


def test_python_single_line() -> None:
    check.assertNotIn('\n', serialize(nested_levels(3), mode='python', pythonWidth=0))


def test_constants_behave_like_strings() -> None:
    check.assertEqual({'mode': 'python'}.get(OptionEnum.MODE), ModeEnum.PYTHON)
    check.assertEqual(str(ModeEnum.JSON), 'json')
    check.assertEqual('{}'.format(ModeEnum.JSON), 'json')
    check.assertEqual(TemplateEnum.CIRCULAR_REFERENCE.format(type_name='dict'), '<circular reference: dict>')


def test_loader_runs_package_without_leaving_modules() -> None:
    names = ['python_debug_copy', 'python_debug_copy.constants', 'python_debug_copy.helper']
    files = ['__init__.py', 'constants.py', 'helper.py']
    sources = [[name, (PACKAGE_DIRECTORY / file).read_text(encoding='utf-8')] for name, file in zip(names, files)]
    before = {name: sys.modules.get(name) for name in names}
    modules = loader.load_modules(sources)
    check.assertEqual({name: sys.modules.get(name) for name in names}, before)
    check.assertIsNot(modules['python_debug_copy.helper'], helper)
    payload_length = int(modules['python_debug_copy.helper'].run({'a': [1]}, json.dumps({'indent': 0}), STORAGE_KEY))
    payload = getattr(builtins, STORAGE_KEY)
    delattr(builtins, STORAGE_KEY)
    check.assertEqual(len(payload), payload_length)
    check.assertEqual(base64.b64decode(payload).decode('utf-8'), '{"a":[1]}')


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    return unittest.TestSuite(
        unittest.FunctionTestCase(test) for name, test in list(globals().items()) if name.startswith('test_') and callable(test)
    )
