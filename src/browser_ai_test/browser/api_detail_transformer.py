from __future__ import annotations

from typing import Any

IGNORED_COMPLEX_TYPES = frozenset(
    {"RequestHeader", "ResponseHeader", "ResultHeader", "Page"}
)


def transform_api_details(data: Any) -> list[dict[str, Any]]:
    """Convert host API details into a flat, comparison-friendly method list."""
    if not isinstance(data, dict):
        return []
    complex_types = _index_complex_types(data.get("complexTypes", []))
    methods: list[dict[str, Any]] = []
    for method in _list(data.get("tableData")):
        if not isinstance(method, dict):
            continue
        methods.append(
            {
                "name": method.get("operationName") or "",
                "request": _flatten_message(method.get("request"), complex_types),
                "response": _flatten_message(method.get("response"), complex_types),
            }
        )
    return methods


def _index_complex_types(items: Any) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in _list(items):
        if not isinstance(item, dict):
            continue
        for key in (item.get("type"), item.get("key"), item.get("name")):
            if isinstance(key, str) and key:
                index[key] = item
    return index


def _flatten_message(
    message: Any, complex_types: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for container in _list(message):
        if not isinstance(container, dict):
            continue
        elements = _list(container.get("elements"))
        if not elements:
            for candidate in (
                container.get("type"),
                container.get("operationKey"),
                container.get("key"),
            ):
                definition = complex_types.get(str(candidate or ""))
                if definition:
                    elements = _list(definition.get("elements"))
                    break
        if elements:
            _flatten_elements(elements, "$", complex_types, result, frozenset())
    return result


def _flatten_elements(
    elements: list[Any],
    parent_path: str,
    complex_types: dict[str, dict[str, Any]],
    output: list[dict[str, Any]],
    type_chain: frozenset[str],
) -> None:
    for element in elements:
        if not isinstance(element, dict):
            continue
        name = element.get("name") or element.get("key")
        if not isinstance(name, str) or not name:
            continue
        element_type = str(element.get("type") or "")
        if element_type in IGNORED_COMPLEX_TYPES:
            continue
        path = f"{parent_path}.{name}"
        inline_elements = _list(element.get("elements"))
        complex_definition = complex_types.get(element_type)
        nested_elements = inline_elements or (
            _list(complex_definition.get("elements")) if complex_definition else []
        )
        if nested_elements:
            if element_type and element_type in type_chain:
                continue
            next_chain = type_chain | ({element_type} if element_type else set())
            _flatten_elements(
                nested_elements, path, complex_types, output, frozenset(next_chain)
            )
            continue
        output.append(
            {
                "path": path,
                "type": element_type or None,
                # Keep the requested external spelling for compatibility.
                "lenth": element.get("length"),
                "required": _required(element),
            }
        )


def _required(element: dict[str, Any]) -> bool:
    required = element.get("required")
    if isinstance(required, bool):
        return required
    return element.get("minOccurs") not in (None, 0, "0")


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
