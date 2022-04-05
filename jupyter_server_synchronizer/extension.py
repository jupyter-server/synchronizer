import asyncio
import pathlib
import uuid

from jupyter_server.extension.application import ExtensionApp
from jupyter_server.gateway.gateway_client import GatewayClient
from jupyter_server.utils import run_sync
from tornado.escape import json_decode
from traitlets import Float, Instance, TraitError, Type, Unicode, default, validate

from .kernel_db import KernelTable
from .kernel_records import KernelRecord, KernelRecordList


class SynchronizerExtension(ExtensionApp):
    """A configurable class for syncing all managers in Jupyter Server."""

    syncing_interval = Float(
        default_value=5.0,
        help="Interval (in seconds) for each call to the periodic syncing method.",
    ).tag(config=True)

    database_filepath = Unicode(
        default_value=":memory:",
        help=(
            "The filesystem path to SQLite Database file "
            "(e.g. /path/to/session_database.db). By default, the session "
            "database is stored in-memory (i.e. `:memory:` setting from sqlite3) "
            "and does not persist when the current Jupyter Server shuts down."
        ),
    ).tag(config=True)

    @validate("database_filepath")
    def _validate_database_filepath(self, proposal):
        value = proposal["value"]
        if value == ":memory:":
            return value
        path = pathlib.Path(value)
        if path.exists():
            # Verify that the database path is not a directory.
            if path.is_dir():
                raise TraitError(
                    "`database_filepath` expected a file path, but the given path is a directory."
                )
            # Verify that database path is an SQLite 3 Database by checking its header.
            with open(value, "rb") as f:
                header = f.read(100)

            if not header.startswith(b"SQLite format 3") and not header == b"":
                raise TraitError("The given file is not an SQLite database file.")
        return value

    kernel_record_class = Type(default_value=KernelRecord, klass=KernelRecord).tag(config=True)

    _kernel_records = KernelRecordList()

    kernel_table_class = Type(default_value=KernelTable, klass=KernelTable)
    kernel_table = Instance(klass=KernelTable)

    @default("kernel_table")
    def _default_kernel_remote_table(self):  # pragma: no cover
        return KernelTable()

    # Awaitable for fetching remote kernels.
    gateway_client_class = Type(default_value=None, klass=GatewayClient, allow_none=True).tag(
        config=True
    )

    gateway_client = Instance(default_value=None, klass=GatewayClient, allow_none=True)

    multi_kernel_manager = Instance(
        klass="jupyter_server.services.kernels.kernelmanager.MappingKernelManager",
        allow_none=True,
    )
    session_manager = Instance(
        klass="jupyter_server.services.sessions.sessionmanager.SessionManager",
        allow_none=True,
    )
    contents_manager = Instance(
        klass="jupyter_server.services.contents.manager.ContentsManager",
        allow_none=True,
    )

    async def fetch_remote_kernels(self) -> None:
        """Fetch kernels from the remote kernel service"""
        r = await self.gateway_client.list_kernels()
        response = json_decode(r.body)
        # Hydrate kernelmanager for all remote kernels
        for item in response:
            kernel = self.kernel_record_class(remote_id=item["id"], alive=True)
            self._kernel_records.update(kernel)

    def fetch_local_kernels(self) -> None:
        """Fetch kernels running in the same process as the Jupyter Server."""
        pass

    def fetch_recorded_kernels(self) -> None:
        """Fetch kernels stored in the local Kernel Database."""
        for k in self.kernel_table.list():
            kernel = self.kernel_record_class(
                kernel_id=k.kernel_id, remote_id=k.remote_id, recorded=True
            )
            self._kernel_records.update(kernel)

    def fetch_managed_kernels(self) -> None:
        """Fetch kernel records from any managed kernels (instances of
        KernelManagers) in the MultiKernelManager."""
        for kernel_id, km in self.multi_kernel_manager._kernels.items():
            kernel = self.kernel_record_class(
                remote_id=km.remote_id, kernel_id=kernel_id, managed=True
            )
            self._kernel_records.update(kernel)

    async def fetch_kernel_records(self):
        if self.gateway_client:
            await self.fetch_remote_kernels()
        self.fetch_local_kernels()
        self.fetch_recorded_kernels()
        self.fetch_managed_kernels()

    def record_kernels(self):
        for kernel in self._kernel_records._records:
            if not kernel.recorded and kernel.kernel_id and kernel.remote_id and kernel.alive:
                self.kernel_table.save(kernel)
                kernel.recorded = True

    def remove_stale_kernels(self):
        for k in self._kernel_records._records:
            if not k.alive:
                self._kernel_records.remove(k)
                if k.recorded:
                    self.kernel_table.delete(kernel_id=k.kernel_id)

    async def hydrate_kernel_managers(self):
        for k in self._kernel_records._records:
            if not k.managed and k.remote_id and k.alive:
                if not k.kernel_id:
                    kernel_id = str(uuid.uuid4())
                    k.kernel_id = kernel_id
                await self.multi_kernel_manager.start_kernel(
                    kernel_id=k.kernel_id, remote_id=k.remote_id
                )
                k.managed = True

    async def delete_stale_sessions(self):
        """Delete sessions that either have no kernel or no content
        found in the server.
        """
        session_list = await self.session_manager.list_sessions()
        mkm = self.multi_kernel_manager
        for session in session_list:
            kid = session["kernel"]["id"]
            known_kids = list(mkm._kernels.keys()) + list(mkm._pending_kernels.keys())
            if kid not in known_kids:
                self.log.info(
                    f"Kernel {kid} found in the session_manager but "
                    f"not in the kernel_manager. Deleting this session."
                )
                # session = await self.get_session(kernel_id=kid)
                self.session_manager.cursor.execute("DELETE FROM session WHERE kernel_id=?", (kid,))
            # Check the contents manager for documents.
            file_exists = self.contents_manager.exists(path=session["path"])
            if not file_exists:
                session_id = session["id"]
                self.log.info(
                    f"The document path for {session_id} was not found. Deleting this session."
                )
                await self.session_manager.delete_session(session_id)

    async def shutdown_kernels_without_sessions(self):
        """Shutdown 'unknown' kernels (found in kernelmanager but
        not the session manager).
        """
        for kernel_id in self.multi_kernel_manager.list_kernel_ids():
            try:
                kernel = await self.session_manager.get_session(kernel_id=kernel_id)
            except Exception:
                try:
                    kernel = self.multi_kernel_manager.get_kernel(kernel_id)
                    if (
                        not kernel.ready.done()
                        or kernel_id in self.session_manager._pending_sessions
                    ):
                        continue
                    self.log.info(
                        f"Kernel {kernel_id} found in the kernel_manager is not "
                        f"found in the session database. Shutting down the kernel."
                    )
                    await self.multi_kernel_manager.shutdown_kernel(kernel_id)
                # Log any failures, but don't raise exceptions.
                except Exception as err2:
                    self.log.info(err2)
                    pass

    async def sync_kernels(self):
        """Synchronize the kernel manager, kernel database, and
        remote kernel service.
        """
        self._kernel_records = KernelRecordList()
        await self.fetch_kernel_records()

        self.remove_stale_kernels()
        await self.hydrate_kernel_managers()
        self.record_kernels()

    async def sync_sessions(self):
        """Synchronize the session database and with the
        multi-kernel_manager by:

        1. Deleting sessions that do not have running
            kernels in the kernel manager
        2. Shutting down kernels in the kernel manager
            that do not have a session associated with them.
        3. Deleting sessions+kernels that do not have content
            found by the contents manager.
        """
        await self.delete_stale_sessions()
        await self.shutdown_kernels_without_sessions()

    async def sync_managers(self):
        """Rehydrate sessions and kernels managers from the remote
        kernel service.
        """
        await self.sync_kernels()
        # await self.sync_sessions()

    async def _regular_syncing(self, interval=5.0):
        """Start regular syncing on a defined interval."""
        while True:
            self.log.info("Synchonizer is starting another loop.")
            # Try to synchonizer. If failed, log the exception.
            try:
                await self.sync_managers()
            except Exception as err:
                self.log.error(f"Synchonizer failed: {err}")
                if self.log.isEnabledFor(10):
                    self.log.exception(err)
            await asyncio.sleep(interval)

    def start_regular_syncing(self):
        """Run regular syncing in a background task."""
        return asyncio.ensure_future(self._regular_syncing(interval=self.syncing_interval))

    def initialize_settings(self):
        self.initialize_configurables()
        return super().initialize_settings()

    def initialize_configurables(self):
        self.update_config(self.serverapp.config)
        if self.gateway_client_class:
            self.gateway_client = self.gateway_client_class.instance()
        self.contents_manager = self.serverapp.contents_manager
        self.multi_kernel_manager = self.serverapp.kernel_manager
        self.session_manager = self.serverapp.session_manager
        self.kernel_table = self.kernel_table_class(
            database_filepath=self.database_filepath,
            kernel_record_class=self.kernel_record_class,
        )
        # Rehydrate the session manager and multi-kernel manager.
        run_sync(self.sync_managers())
        self.start_regular_syncing()
