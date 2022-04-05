from jupyter_server_synchronizer.extension import (
    SynchronizerExtension,
)

from ._version import __version__, version_info


def _jupyter_server_extension_points():  # pragma: no cover
    return [
        {
            "module": "jupyter_server_synchronizer.extension",
            "app": SynchronizerExtension,
        }
    ]
