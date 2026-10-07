"""
Tiny @tool decorator: turns a typed, documented function into a tool spec that both
Anthropic and OpenAI accept. The function stays a normal function you can call directly.

The description and parameter help come from the docstring (":param name: ..." lines);
parameter types come from the type hints.
"""

import inspect
import re
import typing

_TYPES = {str: "string", bool: "boolean", int: "integer", float: "number", dict: "object"}


def _schema(hint) -> dict:
    args = [a for a in typing.get_args(hint) if a is not type(None)]
    if typing.get_origin(hint) is typing.Union and len(args) == 1:  # Optional[X]
        return _schema(args[0])
    if typing.get_origin(hint) is list:
        return {"type": "array", "items": _schema(args[0]) if args else {}}
    return {"type": _TYPES.get(hint, "string")}


def tool(fn):
    doc = inspect.getdoc(fn) or ""
    summary = " ".join(doc.split(":param")[0].split(":returns")[0].split())
    params = re.findall(r":param (\w+):(.*?)(?=:param|:returns|\Z)", doc, re.S)
    helps = {name: " ".join(text.split()) for name, text in params}
    hints = typing.get_type_hints(fn)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {**_schema(hints.get(name, str)), "description": helps.get(name, "")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    fn.spec = {
        "name": fn.__name__,
        "description": summary,
        "input_schema": {"type": "object", "properties": props, "required": required},
    }
    return fn
