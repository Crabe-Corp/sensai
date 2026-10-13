import functools
import inspect
import re
from collections.abc import Callable
from typing import Any, get_args, get_origin
from pydantic import BaseModel, ConfigDict, Field


def _extract_docstring_param_descriptions(docstring: str) -> tuple[str, dict[str, str]]:
    if not docstring:
        return "", {}

    lines = docstring.strip().splitlines()
    summary_lines: list[str] = []
    param_descs: dict[str, str] = {}

    in_summary = True
    current_param: str | None = None

    for raw_line in lines:
        line = raw_line.strip()

        sphinx_match = re.match(r"^:param\s+(?:\w+\s+)?(\w+):\s*(.*)$", line)
        if sphinx_match:
            in_summary = False
            p_name, p_desc = sphinx_match.groups()
            param_descs[p_name] = p_desc
            current_param = p_name
            continue

        google_match = re.match(r"^(\w+)(?:\s*\([^)]+\))?:\s*(.+)$", line)
        if not in_summary and google_match:
            p_name, p_desc = google_match.groups()
            param_descs[p_name] = p_desc
            current_param = p_name
            continue

        if line.lower() in ("args:", "arguments:", "parameters:"):
            in_summary = False
            current_param = None
            continue

        if in_summary:
            summary_lines.append(raw_line)
        elif current_param and line and not line.startswith(":"):
            param_descs[current_param] += f" {line}"

    summary = "\n".join(summary_lines).strip()
    return summary, param_descs


def _python_type_to_json_type(annotation: Any) -> tuple[str, dict[str, Any] | None]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return "string", None

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and type(None) in args:
        non_none_args = [a for a in args if a is not type(None)]
        if non_none_args:
            return _python_type_to_json_type(non_none_args[0])

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "object", annotation.model_json_schema()

    type_mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    if annotation in type_mapping:
        return type_mapping[annotation], None

    if origin in (list, tuple, set):
        return "array", None
    if origin is dict:
        return "object", None

    return "string", None


def extract_tool_schema(func: Callable[..., Any], name: str | None = None, description: str | None = None) -> dict[str, Any]:
    tool_name = name or func.__name__
    raw_doc = inspect.cleandoc(func.__doc__ or "")
    doc_summary, doc_params = _extract_docstring_param_descriptions(raw_doc)
    tool_desc = description or doc_summary or f"Outil {tool_name}"

    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        json_type, custom_schema = _python_type_to_json_type(param.annotation)

        if custom_schema:
            prop = dict(custom_schema)
        else:
            prop: dict[str, Any] = {"type": json_type}

        if param_name in doc_params:
            prop["description"] = doc_params[param_name]

        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = prop

    return {
        "name": tool_name,
        "description": tool_desc,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    handler: Callable[..., Any] = Field(exclude=True)

    def to_ollama_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        func: Callable[..., Any] | ToolDefinition,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ToolDefinition:
        if isinstance(func, ToolDefinition):
            self._tools[func.name] = func
            return func

        schema = extract_tool_schema(func, name=name, description=description)
        tool_def = ToolDefinition(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["parameters"],
            handler=func,
        )
        self._tools[tool_def.name] = tool_def
        return tool_def

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def to_ollama_tools(self) -> list[dict[str, Any]]:
        return [tool.to_ollama_dict() for tool in self._tools.values()]

    def register_mcp_client(self, client: Any, prefix: str = "") -> list[ToolDefinition]:
        if hasattr(client, "register_into_registry"):
            return client.register_into_registry(self, prefix=prefix)
        return []

    def unregister_tools(self, names: list[str]) -> None:
        for name in names:
            self._tools.pop(name, None)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def clear(self) -> None:
        self._tools.clear()


default_registry = ToolRegistry()


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    registry: ToolRegistry | None = None,
) -> Any:
    target_registry = registry or default_registry

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_def = target_registry.register(fn, name=name, description=description)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.tool_definition = tool_def
        wrapper.to_ollama_dict = tool_def.to_ollama_dict
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
