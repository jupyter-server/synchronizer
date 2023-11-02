"""Trait utils."""
import inspect
from typing import Any

from traitlets import TraitType


class Awaitable(TraitType[Any, Any]):
    """An awaitable object trait."""

    info_text = "an awaitable"

    def validate(self, obj: Any, value: Any) -> Any:
        """Validate the object"""
        if not inspect.iscoroutinefunction(value) and not inspect.isawaitable(value):
            raise self.error(obj, value)
        return value
