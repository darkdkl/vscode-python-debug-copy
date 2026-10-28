from __future__ import annotations

import enum
import types

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, enum.Enum):
        __str__ = str.__str__
        __format__ = str.__format__


class ModeEnum(StrEnum):
    JSON = 'json'
    PYTHON = 'python'


class OptionEnum(StrEnum):
    MODE = 'mode'
    INDENT = 'indent'
    ENSURE_ASCII = 'ensureAscii'
    PYTHON_WIDTH = 'pythonWidth'
    SORT_KEYS = 'sortKeys'
    MAX_DEPTH = 'maxDepth'
    SKIP_PRIVATE_ATTRIBUTES = 'skipPrivateAttributes'
    INCLUDE_TYPE_NAME = 'includeTypeName'
    DATA_FRAME_ORIENT = 'dataFrameOrient'


class DefaultEnum(enum.IntEnum):
    INDENT = 2
    PYTHON_WIDTH = 100
    MAX_DEPTH = 100


class DataFrameOrientEnum(StrEnum):
    RECORDS = 'records'


class JsonLiteralEnum(StrEnum):
    NULL = 'null'
    TRUE = 'true'
    FALSE = 'false'
    NAN = 'NaN'
    INFINITY = 'Infinity'
    NEGATIVE_INFINITY = '-Infinity'


class TextEncodingEnum(StrEnum):
    UTF8 = 'utf-8'
    ASCII = 'ascii'
    SURROGATE_PASS = 'surrogatepass'


class TemplateEnum(StrEnum):
    QUALIFIED_NAME = '{module}.{name}'
    MANGLED_NAME = '_{class_name}{attribute}'
    UNIQUE_KEY = '{key} ({counter})'
    UNREPRESENTABLE = '<unrepresentable {type_name}: {error}>'
    MAX_DEPTH_REACHED = '<max depth {max_depth} reached: {type_name}>'
    CIRCULAR_REFERENCE = '<circular reference: {type_name}>'
    CONVERSION_ERROR = '<error converting {type_name}: {error}>'


class ResultKeyEnum(StrEnum):
    TYPE_NAME = '__type__'
    EXCEPTION_TYPE = 'type'
    EXCEPTION_ARGS = 'args'


class AttributeEnum(StrEnum):
    MODULE = '__module__'
    QUALNAME = '__qualname__'
    DICT = '__dict__'
    SLOTS = '__slots__'
    WEAKREF = '__weakref__'
    NAMEDTUPLE_AS_DICT = '_asdict'
    NAMEDTUPLE_FIELDS = '_fields'
    DATACLASS_FIELDS = '__dataclass_fields__'
    PYDANTIC_DUMP = 'model_dump'
    PYDANTIC_FIELDS = 'model_fields'
    PYDANTIC_V1_DICT = 'dict'
    PYDANTIC_V1_FIELDS = '__fields__'
    ATTRS_FIELDS = '__attrs_attrs__'
    NUMPY_TO_LIST = 'tolist'
    NUMPY_ITEM = 'item'
    SQLALCHEMY_STATE = '_sa_instance_state'


class ModuleEnum(StrEnum):
    BUILTINS = 'builtins'
    NUMPY = 'numpy'
    PANDAS = 'pandas'
    PATHLIB = 'pathlib'
    IPADDRESS = 'ipaddress'


class PandasTypeEnum(StrEnum):
    NAT = 'NaTType'
    NA = 'NAType'
    DATA_FRAME = 'DataFrame'
    SERIES = 'Series'
    INDEX = 'Index'
    PERIOD = 'Period'


class SymbolEnum(StrEnum):
    EMPTY = ''
    DOT = '.'
    UNDERSCORE = '_'
    DUNDER = '__'


PLAIN_TYPES = (type(None), bool, int, str)
INFINITIES = (float('inf'), float('-inf'))
CALLABLE_OR_MODULE_TYPES = (type, types.FunctionType, types.BuiltinFunctionType, types.MethodType, types.ModuleType)
JSON_COMPACT_SEPARATORS = (',', ':')
SLOT_DESCRIPTORS = (AttributeEnum.DICT, AttributeEnum.WEAKREF)
