# Python Debug Copy

Copy variables from the Python debugger in VS Code as JSON or as a Python dict, with all nested values. Plus Copy Name and Copy Path for any node of the Variables and Watch views.

Right-click a variable while stopped at a breakpoint:

| Command | Result for `catalog.element` (JSON shown on one line) |
| --- | --- |
| **Copy Name** | `element` |
| **Copy Path** | `catalog.element` |
| **Copy as JSON** | `{"code": "E1", "meta": {"code": 5, "tags": ["a", "b"]}}` |
| **Copy as Python dict** | `{'code': 'E1', 'meta': {'code': 5, 'tags': ['a', 'b']}}` |
| **Open as JSON** | the same JSON in a new editor tab |

### Copy Name and Copy Path

**Copy Name** copies the name of an attribute, a list index or a dict key, without quotes: `'user_id'` becomes `user_id`.

**Copy Path** copies the path from the root variable: attributes are joined with `.`, keys and indices go in brackets.

```python
catalog.element.code
catalog['element']['code']
catalog.element.meta['code']
items[0]
```

### Copy as JSON and Copy as Python dict

The value is converted inside the debugged program with `json` and `pprint`, and every nested level is copied.

- Objects become dicts: dataclasses, pydantic v1 and v2 models, attrs classes, named tuples, and plain objects (`__dict__` and `__slots__`).
- In JSON, `datetime`, `date` and `time` become ISO strings, `timedelta`, `Decimal` and `UUID` become strings, `bytes` become text, sets and tuples become lists. In the Python dict mode they stay Python objects: `datetime.date(2024, 1, 2)`, `Decimal('1.10')`, `(1, 2)`. Paste such a result where the names it uses, like `datetime` or `Decimal`, are imported.
- `Enum` members become their values, `Path` becomes a string, in both modes.
- Exceptions become `{"type": "ValueError", "args": ["boom", 42]}` in JSON, and stay `ValueError('boom', 42)` in the Python dict mode.
- numpy arrays and scalars, pandas DataFrames, Series and Timestamps are supported.
- Circular references become `"<circular reference: Type>"`. In JSON, `NaN`, `Infinity` and pandas `NaT` become `null`; in the Python dict mode they stay `nan`, `inf` and `NaT`.

You can also select an expression in the editor while debugging and pick **Copy as JSON** or **Copy as Python dict** from the context menu, or run `Python Debug Copy: Copy as JSON` from the Command Palette and type an expression, for example `response.json()`.

### Install

Search for **Python Debug Copy** in the Extensions view of VS Code, or run `code --install-extension dark-dmake.python-debug-copy`.

You can also download `python-debug-copy-<version>.vsix` from the [releases](https://github.com/darkdkl/vscode-python-debug-copy/releases), and run `code --install-extension python-debug-copy-<version>.vsix`.

The commands appear in debug sessions of the [Python Debugger](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy) extension.

### Settings

| Setting | Default | Description |
| --- | --- | --- |
| `pythonDebugCopy.json.indent` | `2` | JSON indentation. `0` writes everything on one line |
| `pythonDebugCopy.json.ensureAscii` | `false` | Escape non-ASCII characters as `\uXXXX` |
| `pythonDebugCopy.python.width` | `100` | Line width of the Python dict. `0` writes everything on one line |
| `pythonDebugCopy.sortKeys` | `false` | Sort dict keys |
| `pythonDebugCopy.maxDepth` | `100` | Values nested deeper are replaced with a placeholder |
| `pythonDebugCopy.skipPrivateAttributes` | `false` | Skip object attributes starting with `_`. Dict keys are never skipped |
| `pythonDebugCopy.includeTypeName` | `false` | Add a `"__type__"` key with the class name to converted objects |
| `pythonDebugCopy.dataFrameOrient` | `records` | How DataFrames are converted, as in `DataFrame.to_dict(orient=...)` |

### Known limitations

- Copy Path and the Copy as commands use the expression the debugger reports for a node. Some nodes have none, for example `special variables`, set items, or dict keys like enum members, and can't be copied.
- For an attribute whose name isn't a Python identifier, for example one set with `setattr(obj, 'has space', ...)`, the path is built with `getattr(obj, 'has space')` for the attribute and its direct children only. Deeper nodes below it get the path the debugger reports, which can't be evaluated.
- Converting a value runs code in the debugged program: pydantic `model_dump()` and pandas `to_dict()` are called. Properties of plain objects are not called, only `__dict__` and `__slots__` are read.
- Generators and other iterators are not read, so they aren't used up.
