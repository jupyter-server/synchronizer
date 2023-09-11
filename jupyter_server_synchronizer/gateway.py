"""Gateway utils."""
from __future__ import annotations

from typing import TYPE_CHECKING

from jupyter_server.gateway.gateway_client import gateway_request
from tornado.escape import json_decode

if TYPE_CHECKING:
    from jupyter_server_synchronizer import SynchronizerSessionManager


async def fetch_gateway_kernels(synchronizer: SynchronizerSessionManager) -> None:
    """Fetch running kernels from a Kernel/Enterprise Gateway."""
    mkm = synchronizer.kernel_manager
    response = await gateway_request(mkm.kernels_url, method="GET")
    kernels = json_decode(response.body)
    # Hydrate kernelmanager for all remote kernels
    for k in kernels:
        kernel = synchronizer.kernel_record_class(
            kernel_id=k["id"], kernel_name=k["name"], alive=True
        )
        synchronizer._kernel_records.update(kernel)
