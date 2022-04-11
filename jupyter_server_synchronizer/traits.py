import inspect

from traitlets import TraitType


class Awaitable(TraitType):

    info_text = "an awaitable"

    def validate(self, obj, value):
        if not inspect.iscoroutinefunction(value) and not inspect.isawaitable(value):
            raise self.error(obj, value)
        return value
