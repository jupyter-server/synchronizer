import asyncio
import pathlib
import uuid

from jupyter_server.extension.application import ExtensionApp
from jupyter_server.utils import ensure_async, run_sync
from traitlets import (
    Bool,
    Float,
    Instance,
    TraitError,
    Type,
    Unicode,
    default,
    validate,
)

from .handlers import handlers
from .kernel_db import KernelTable
from .kernel_records import KernelRecord, KernelRecordList
from .traits import Awaitable


class SynchronizerExtension(ExtensionApp):
    """A Jupyter Server extension for syncing all managers in Jupyter Server."""

    name = "synchronizer"
    handlers = handlers

    autosync = Bool(
        default_value=False,
        help="If True, the extension will periodically synchronize the server automatically.",
    ).tag(config=True)

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

    fetch_running_kernels = Awaitable(
        help="The coroutine function used to fetch and record running kernels that might not be found/managed by Jupyter Server (i.e. they are managed by a remote Kernel Gateway). "
    ).tag(config=True)

    @default("fetch_running_kernels")
    def default_fetch_running_kernels(self):
        async def fetch_running_kernels(self):
            kernels = await ensure_async(self.multi_kernel_manager.list_kernels())
            # Hydrate kernelmanager for all remote kernels
            for k in kernels:
                kernel = self.kernel_record_class(kernel_id=k["id"], alive=True)
                self._kernel_records.update(kernel)

        return fetch_running_kernels

    multi_kernel_manager = Instance(
        klass="jupyter_server.services.kernels.kernelmanager.MappingKernelManager",
    )

    @default("multi_kernel_manager")
    def _default_multi_kernel_manager(self):
        return self.serverapp.kernel_manager

    contents_manager = Instance(
        klass="jupyter_server.services.contents.manager.ContentsManager",
    )

    @default("contents_manager")
    def _default_contents_manager(self):
        return self.serverapp.contents_manager

    session_manager = Instance(
        klass="jupyter_server.services.sessions.sessionmanager.SessionManager",
    )

    @default("session_manager")
    def _default_session_manager(self):
        return self.serverapp.session_manager

    def fetch_recorded_kernels(self) -> None:
        """Fetch kernels stored in the local Kernel Database."""
        for record in self.kernel_table.list():
            record.recorded = True
            self._kernel_records.update(record)

    def fetch_managed_kernels(self) -> None:
        """Fetch kernel records from any managed kernels (instances of
        KernelManagers) in the MultiKernelManager.
        """
        for km in self.multi_kernel_manager._kernels.values():
            record = self.kernel_record_class.from_manager(km)
            self._kernel_records.update(record)

    async def fetch_kernel_records(self):
        """Fetch all the information that can be found about
        kernels started by this server.
        """
        await self.fetch_running_kernels(self)
        self.fetch_recorded_kernels()
        self.fetch_managed_kernels()
        # Log all kernel records seen at this stage
        self.log.debug(self._kernel_records)

    def record_kernels(self):
        """Record the current kernels to the kernel database."""
        for kernel in self._kernel_records._records:
            conditions = [
                # Kernel isn't already recorded
                not kernel.recorded,
                # Kernel has all identifiers
                all(kernel.get_identifier_values()),
                # Kernel is still running
                kernel.alive,
            ]
            if all(conditions):
                self.kernel_table.save(kernel)
                kernel.recorded = True

    def remove_stale_kernels(self):
        """Remove kernels from the database that are no longer running."""
        for k in self._kernel_records._records:
            if not k.alive:
                self._kernel_records.remove(k)
                if k.recorded:
                    self.kernel_table.delete(kernel_id=k.kernel_id)

    async def hydrate_kernel_managers(self):
        """Create KernelManagers for kernels found for this
        server but are not yet managed.
        """
        for k in self._kernel_records._records:
            if not k.managed and k.alive:
                if not k.kernel_id:
                    kernel_id = str(uuid.uuid4())
                    k.kernel_id = kernel_id
                identifiers = k.get_active_identifiers()
                await self.multi_kernel_manager.start_kernel(**identifiers)
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
                self.log.debug(
                    f"Kernel {kid} found in the session_manager but "
                    f"not in the kernel_manager. Deleting this session."
                )
                # session = await self.get_session(kernel_id=kid)
                self.session_manager.cursor.execute("DELETE FROM session WHERE kernel_id=?", (kid,))
            # Check the contents manager for documents.
            file_exists = self.contents_manager.exists(path=session["path"])
            if not file_exists:
                session_id = session["id"]
                self.log.debug(
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
                    self.log.debug(
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
        self.log.debug("Synchronizing kernel records.")
        await self.sync_kernels()
        self.log.debug("Synchronizing kernel sessions.")
        await self.sync_sessions()

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
        self.kernel_table = self.kernel_table_class(
            database_filepath=self.database_filepath,
            kernel_record_class=self.kernel_record_class,
        )
        # Run the synchronizer once before starting the webapp, to
        # ensure we start with the most accurate state.
        run_sync(self.sync_managers())
        if self.autosync:
            self.start_regular_syncing()
