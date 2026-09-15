"""Model adapter contracts and mock-only Phase 4B-7 implementation."""

from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Final

from .base import AdapterRequest, AdapterResponse, ModelAdapter

_EAGER_EXPORTS: Final[frozenset[str]] = frozenset(
    {"AdapterRequest", "AdapterResponse", "ModelAdapter"}
)
_LAZY_EXPORTS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "MockAdapter": (".mock", "MockAdapter"),
        "MockScriptStep": (".mock", "MockScriptStep"),
        "validate_adapter_response": (".mock", "validate_adapter_response"),
    }
)

__all__ = [
    "AdapterRequest",
    "AdapterResponse",
    "MockAdapter",
    "MockScriptStep",
    "ModelAdapter",
    "validate_adapter_response",
]

if _EAGER_EXPORTS & set(_LAZY_EXPORTS):
    raise RuntimeError("adapter facade eager and lazy exports overlap")

if _EAGER_EXPORTS | set(_LAZY_EXPORTS) != set(__all__):
    missing = sorted(set(__all__) - (_EAGER_EXPORTS | set(_LAZY_EXPORTS)))
    extra = sorted((_EAGER_EXPORTS | set(_LAZY_EXPORTS)) - set(__all__))
    raise RuntimeError(f"adapter facade public API drift: missing={missing}, extra={extra}")


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    module = import_module(module_name, __name__)
    try:
        value = vars(module)[attribute_name]
    except KeyError as error:
        raise ImportError(
            f"lazy adapter facade target is missing: {module.__name__}.{attribute_name}"
        ) from error
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
