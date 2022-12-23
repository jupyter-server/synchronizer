"""Trait utils."""
import inspect

from traitlets import TraitType


class Awaitable(TraitType):
    """An awaitable object trait."""

    info_text = "an awaitable"

    def validate(self, obj, value):
        """Validate the object"""
        if not inspect.iscoroutinefunction(value) and not inspect.isawaitable(value):
            raise self.error(obj, value)
        return value
