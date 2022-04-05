from jupyter_server_synchronizer.extension import SynchronizerExtension


def _jupyter_server_extension_points():  # pragma: no cover
    return [
        {
            "module": "jupyter_server_synchronizer.extension",
            "app": SynchronizerExtension,
        }
    ]
