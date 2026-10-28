from __future__ import annotations

import base64
import builtins
import collections.abc
import dataclasses
import datetime
import decimal
import enum
import json
import pprint
import uuid
from typing import Any, Iterable

from python_debug_copy.constants import (
    CALLABLE_OR_MODULE_TYPES,
    INFINITIES,
    JSON_COMPACT_SEPARATORS,
    PLAIN_TYPES,
    SLOT_DESCRIPTORS,
    AttributeEnum,
    DataFrameOrientEnum,
    DefaultEnum,
    JsonLiteralEnum,
    ModeEnum,
    ModuleEnum,
    OptionEnum,
    PandasTypeEnum,
    ResultKeyEnum,
    SymbolEnum,
    TemplateEnum,
    TextEncodingEnum,
)


def run(value: Any, options_json: str, storage_key: str) -> str:
    options = json.loads(options_json)
    text = render(value, options)
    encoded = text.encode(TextEncodingEnum.UTF8, TextEncodingEnum.SURROGATE_PASS)
    payload = base64.b64encode(encoded).decode(TextEncodingEnum.ASCII)
    setattr(builtins, storage_key, payload)
    return str(len(payload))


def render(value: Any, options: dict[str, Any]) -> str:
    data = Normalizer(options).convert(value)

    if options.get(OptionEnum.MODE, ModeEnum.JSON) == ModeEnum.PYTHON:
        width = int(options.get(OptionEnum.PYTHON_WIDTH, DefaultEnum.PYTHON_WIDTH))
        if width <= 0:
            return repr(data)
        try:
            return pprint.pformat(data, indent=1, width=width, sort_dicts=bool(options.get(OptionEnum.SORT_KEYS)))
        except TypeError:
            return pprint.pformat(data, indent=1, width=width)

    indent = int(options.get(OptionEnum.INDENT, DefaultEnum.INDENT))
    compact = indent <= 0
    ensure_ascii = bool(options.get(OptionEnum.ENSURE_ASCII))
    separators = JSON_COMPACT_SEPARATORS if compact else None
    try:
        return json.dumps(
            data,
            indent=None if compact else indent,
            ensure_ascii=ensure_ascii,
            separators=separators,
            sort_keys=bool(options.get(OptionEnum.SORT_KEYS)),
            default=str,
        )
    except TypeError:
        return json.dumps(data, indent=None if compact else indent, ensure_ascii=ensure_ascii, separators=separators, default=str)


class Normalizer:
    def __init__(self, options: dict[str, Any]) -> None:
        self.python_mode = options.get(OptionEnum.MODE) == ModeEnum.PYTHON
        self.max_depth = int(options.get(OptionEnum.MAX_DEPTH, DefaultEnum.MAX_DEPTH))
        self.skip_private = bool(options.get(OptionEnum.SKIP_PRIVATE_ATTRIBUTES))
        self.include_type = bool(options.get(OptionEnum.INCLUDE_TYPE_NAME))
        self.data_frame_orient = options.get(OptionEnum.DATA_FRAME_ORIENT, DataFrameOrientEnum.RECORDS.value)
        self._ids_on_path: set[int] = set()

    @staticmethod
    def _type_name(value: Any) -> str:
        value_type = type(value)
        module = getattr(value_type, AttributeEnum.MODULE, SymbolEnum.EMPTY)
        name = getattr(value_type, AttributeEnum.QUALNAME, value_type.__name__)
        if module in (ModuleEnum.BUILTINS, SymbolEnum.EMPTY, None):
            return name
        return TemplateEnum.QUALIFIED_NAME.format(module=module, name=name)

    @staticmethod
    def _root_module(value: Any) -> str:
        module = getattr(type(value), AttributeEnum.MODULE, SymbolEnum.EMPTY) or SymbolEnum.EMPTY
        return module.partition(SymbolEnum.DOT)[0]

    @staticmethod
    def _is_enum(value: Any) -> bool:
        return isinstance(value, enum.Enum)

    def _safe_repr(self, value: Any) -> str:
        try:
            return repr(value)
        except Exception as error:
            return TemplateEnum.UNREPRESENTABLE.format(type_name=self._type_name(value), error=error)

    def _normalize_key(self, key: Any) -> Any:
        if self._is_enum(key):
            return self._normalize_key(key.value)
        if self.python_mode:
            if key is None or isinstance(key, (str, bool, int, float)):
                return key
            normalized = self.convert(key)
            try:
                hash(normalized)
                return normalized
            except TypeError:
                return self._safe_repr(key)
        if isinstance(key, str):
            return str(key)
        if key is None:
            return JsonLiteralEnum.NULL.value
        if isinstance(key, bool):
            return (JsonLiteralEnum.TRUE if key else JsonLiteralEnum.FALSE).value
        if isinstance(key, int):
            return str(int(key))
        if isinstance(key, float):
            if key != key:
                return JsonLiteralEnum.NAN.value
            if key in INFINITIES:
                return (JsonLiteralEnum.INFINITY if key > 0 else JsonLiteralEnum.NEGATIVE_INFINITY).value
            return repr(float(key))
        return str(key)

    def _mapping(self, items: Iterable[tuple[Any, Any]], depth: int, type_name: str | None = None) -> dict[Any, Any]:
        entries = [(original_key, self._normalize_key(original_key), item_value) for original_key, item_value in items]
        key_owners: dict[Any, int] = {}
        for index, (original_key, normalized_key, _) in enumerate(entries):
            owner_index = key_owners.get(normalized_key)
            if owner_index is None:
                key_owners[normalized_key] = index
                continue
            owner_original, owner_normalized, _ = entries[owner_index]
            if type(normalized_key) is type(original_key) and type(owner_normalized) is not type(owner_original):
                key_owners[normalized_key] = index

        result: dict[Any, Any] = {}
        if type_name and self.include_type:
            result[ResultKeyEnum.TYPE_NAME.value] = type_name
        for index, (original_key, normalized_key, item_value) in enumerate(entries):
            result_key = normalized_key
            if key_owners[normalized_key] != index or result_key in result:
                fallback = self._safe_repr(original_key)
                result_key, counter = fallback, 2
                while result_key in result or result_key in key_owners:
                    result_key, counter = TemplateEnum.UNIQUE_KEY.format(key=fallback, counter=counter), counter + 1
            result[result_key] = self.convert(item_value, depth + 1)
        return result

    def _instance_attributes(self, value: Any) -> list[tuple[str, Any]]:
        found: list[tuple[str, Any]] = []
        seen_names: set[str] = set()
        instance_dict = getattr(value, AttributeEnum.DICT, None)
        if isinstance(instance_dict, dict):
            for name, attribute in instance_dict.items():
                if isinstance(name, str):
                    seen_names.add(name)
                    found.append((name, attribute))
        for cls in type(value).__mro__:
            slots = cls.__dict__.get(AttributeEnum.SLOTS, ())
            if isinstance(slots, str):
                slots = (slots,)
            for slot in slots:
                if slot in seen_names or slot in SLOT_DESCRIPTORS:
                    continue
                if slot.startswith(SymbolEnum.DUNDER) and not slot.endswith(SymbolEnum.DUNDER):
                    slot = TemplateEnum.MANGLED_NAME.format(class_name=cls.__name__.lstrip(SymbolEnum.UNDERSCORE), attribute=slot)
                try:
                    found.append((slot, getattr(value, slot)))
                    seen_names.add(slot)
                except AttributeError:
                    pass
        attributes = []
        for name, attribute in found:
            if name.startswith(SymbolEnum.DUNDER) and name.endswith(SymbolEnum.DUNDER):
                continue
            if self.skip_private and name.startswith(SymbolEnum.UNDERSCORE):
                continue
            if name == AttributeEnum.SQLALCHEMY_STATE:
                continue
            attributes.append((name, attribute))
        return attributes

    def convert(self, value: Any, depth: int = 0) -> Any:
        value_type = type(value)
        if value_type in PLAIN_TYPES:
            return value
        if value_type is float:
            if not self.python_mode and (value != value or value in INFINITIES):
                return None
            return value

        if depth > self.max_depth:
            return TemplateEnum.MAX_DEPTH_REACHED.format(max_depth=self.max_depth, type_name=self._type_name(value))

        value_id = id(value)
        if value_id in self._ids_on_path:
            return TemplateEnum.CIRCULAR_REFERENCE.format(type_name=self._type_name(value))
        self._ids_on_path.add(value_id)
        try:
            return self._convert_value(value, depth)
        except Exception as error:
            return TemplateEnum.CONVERSION_ERROR.format(type_name=self._type_name(value), error=error)
        finally:
            self._ids_on_path.discard(value_id)

    def _convert_value(self, value: Any, depth: int) -> Any:
        python_mode = self.python_mode

        if self._is_enum(value):
            return self.convert(value.value, depth + 1)
        if isinstance(value, str):
            return str(value)
        if isinstance(value, bool):
            return bool(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return self.convert(float(value), depth)

        if isinstance(value, (dict, collections.abc.Mapping)):
            return self._mapping(value.items(), depth)

        if isinstance(value, tuple) and hasattr(value, AttributeEnum.NAMEDTUPLE_AS_DICT) and hasattr(value, AttributeEnum.NAMEDTUPLE_FIELDS):
            return self._mapping(value._asdict().items(), depth, self._type_name(value))

        if isinstance(value, (list, tuple)):
            items = [self.convert(item, depth + 1) for item in value]
            return tuple(items) if (python_mode and isinstance(value, tuple)) else items

        if isinstance(value, (set, frozenset)):
            items = [self.convert(item, depth + 1) for item in value]
            try:
                items.sort()
            except TypeError:
                pass
            if python_mode:
                try:
                    return set(items) if isinstance(value, set) else frozenset(items)
                except TypeError:
                    return items
            return items

        if isinstance(value, (bytes, bytearray, memoryview)):
            raw_bytes = bytes(value)
            if python_mode:
                return raw_bytes
            try:
                return raw_bytes.decode(TextEncodingEnum.UTF8)
            except UnicodeDecodeError:
                return repr(raw_bytes)

        root_module = self._root_module(value)
        type_name = type(value).__name__

        if root_module == ModuleEnum.PANDAS and type_name == PandasTypeEnum.NAT:
            return value if python_mode else None

        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            return value if python_mode else value.isoformat()
        if isinstance(value, (datetime.timedelta, decimal.Decimal, complex, uuid.UUID)):
            return value if python_mode else str(value)

        if root_module == ModuleEnum.NUMPY:
            if hasattr(value, AttributeEnum.NUMPY_TO_LIST):
                return self.convert(value.tolist(), depth + 1)
            if hasattr(value, AttributeEnum.NUMPY_ITEM):
                return self.convert(value.item(), depth + 1)

        if root_module == ModuleEnum.PANDAS:
            if type_name == PandasTypeEnum.DATA_FRAME:
                try:
                    frame_data = value.to_dict(orient=self.data_frame_orient)
                except Exception:
                    frame_data = value.to_dict()
                return self.convert(frame_data, depth + 1)
            if type_name == PandasTypeEnum.SERIES:
                return self.convert(value.to_dict(), depth + 1)
            if type_name == PandasTypeEnum.INDEX:
                return self.convert(list(value), depth + 1)
            if type_name == PandasTypeEnum.PERIOD:
                return self._safe_repr(value) if python_mode else str(value)
            if type_name == PandasTypeEnum.NA:
                return None

        if root_module in (ModuleEnum.PATHLIB, ModuleEnum.IPADDRESS):
            return str(value)

        if isinstance(value, BaseException):
            if python_mode:
                return value
            exception = {
                ResultKeyEnum.EXCEPTION_TYPE.value: self._type_name(value),
                ResultKeyEnum.EXCEPTION_ARGS.value: [self.convert(arg, depth + 1) for arg in value.args],
            }
            for name, attribute in self._instance_attributes(value):
                if name not in exception:
                    exception[name] = self.convert(attribute, depth + 1)
            return exception

        if hasattr(type(value), AttributeEnum.DATACLASS_FIELDS) and not isinstance(value, type):
            fields = [(field.name, getattr(value, field.name)) for field in dataclasses.fields(value) if hasattr(value, field.name)]
            return self._mapping(fields, depth, self._type_name(value))

        if hasattr(value, AttributeEnum.PYDANTIC_DUMP) and hasattr(type(value), AttributeEnum.PYDANTIC_FIELDS):
            try:
                return self._mapping(value.model_dump().items(), depth, self._type_name(value))
            except Exception:
                pass
        if hasattr(value, AttributeEnum.PYDANTIC_V1_DICT) and hasattr(type(value), AttributeEnum.PYDANTIC_V1_FIELDS):
            try:
                return self._mapping(value.dict().items(), depth, self._type_name(value))
            except Exception:
                pass

        attrs_fields = getattr(type(value), AttributeEnum.ATTRS_FIELDS, None)
        if attrs_fields is not None:
            try:
                fields = [(field.name, getattr(value, field.name)) for field in attrs_fields]
                return self._mapping(fields, depth, self._type_name(value))
            except Exception:
                pass

        if isinstance(value, CALLABLE_OR_MODULE_TYPES):
            return self._safe_repr(value)

        attributes = self._instance_attributes(value)
        if attributes or hasattr(value, AttributeEnum.DICT):
            return self._mapping(attributes, depth, self._type_name(value))

        if isinstance(value, (collections.abc.Sequence, collections.abc.Set)) and not isinstance(value, str):
            return [self.convert(item, depth + 1) for item in value]

        if isinstance(value, range):
            return list(value)

        return self._safe_repr(value) if python_mode else str(value)
