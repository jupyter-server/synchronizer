"""A Jupyter Server Session Manager that rehydrates sessions/kernels on server restart."""
from __future__ import annotations

import asyncio
import typing as t
import uuid

from jupyter_server.services.sessions.sessionmanager import KernelSessionRecordList, SessionManager
from traitlets import Bool, Float, Instance, Type, default

from .gateway import fetch_gateway_kernels
from .kernel_db import KernelTable
from .kernel_records import KernelRecord, KernelRecordList
from .traits import Awaitable

# mypy: disable-error-code="no-untyped-call"


class SynchronizerSessionManager(SessionManager):  # type:ignore[misc]
    """A Jupyter Server Session Manager that rehydrates sessions/kernels on server restart."""

    sync_before_server = Bool(
        default_value=False,
        help="Run the synchronizer once before the underlying Jupyter Server starts?",
    ).tag(config=True)

    autosync = Bool(
        default_value=False,
        help="If True, the extension will periodically synchronize the server automatically.",
    ).tag(config=True)

    syncing_interval = Float(
        default_value=5.0,
        help="Interval (in seconds) for each call to the periodic syncing method.",
    ).tag(config=True)

    kernel_record_class = Type(default_value=KernelRecord, klass=KernelRecord).tag(config=True)

    _kernel_records = KernelRecordList()

    kernel_table_class = Type(default_value=KernelTable, klass=KernelTable)
    kernel_table = Instance(klass=KernelTable)

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        """Initialize the manager."""
        super().__init__(*args, **kwargs)
        self._pending_sessions = KernelSessionRecordList()
        self.kernel_table = self.kernel_table_class(
            database_filepath=self.database_filepath,
            kernel_record_class=self.kernel_record_class,
        )

    @default("kernel_table")
    def _default_kernel_remote_table(self) -> KernelTable:  # pragma: no cover
        return KernelTable()

    fetch_running_kernels = Awaitable(
        help=(
            "The coroutine function used to fetch and record running kernels "
            "that might not be found/managed by Jupyter Server (i.e. they "
            "are managed by a remote Kernel Gateway)."
        )
    ).tag(config=True)

    @default("fetch_running_kernels")
    def _default_fetch_running_kernels(self) -> t.Callable[..., t.Any]:
        return fetch_gateway_kernels

    def fetch_recorded_kernels(self) -> None:
        """Fetch kernels stored in the local Kernel Database."""
        for record in self.kernel_table.list():
            record.recorded = True
            self._kernel_records.update(record)

    def fetch_managed_kernels(self) -> None:
        """Fetch kernel records from any managed kernels (instances of
        KernelManagers) in the MultiKernelManager.
        """
        for km in self.kernel_manager._kernels.values():
            record = self.kernel_record_class.from_manager(km)
            self._kernel_records.update(record)

    async def fetch_kernel_records(self) -> None:
        """Fetch all the information that can be found about
        kernels started by this server.
        """
        await self.fetch_running_kernels(self)
        self.fetch_recorded_kernels()
        self.fetch_managed_kernels()
        # Log all kernel records seen at this stage
        self.log.debug(str(self._kernel_records))

    def record_kernels(self) -> None:
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
                try:
                    self.kernel_table.save(kernel)
                    kernel.recorded = True
                except Exception as e:
                    self.log.error("Could not record kernel. %s", kernel)
                    self.log.error(e)

    def remove_stale_kernels(self) -> None:
        """Remove kernels from the database that are no longer running."""
        for k in self._kernel_records._records:
            if not k.alive:
                try:
                    self._kernel_records.remove(k)
                    if k.recorded:
                        self.kernel_table.delete(kernel_id=k.kernel_id)
                except Exception as e:
                    self.log.error("Could not remove kernel from records: %s", k)
                    self.log.error(e)

    async def hydrate_kernel_managers(self) -> None:
        """Create KernelManagers for kernels found for this
        server but are not yet managed.
        """
        for k in self._kernel_records._records:
            if not k.managed and k.alive:
                if not k.kernel_id:
                    kernel_id = str(uuid.uuid4())
                    k.kernel_id = kernel_id
                kwargs = k.get_active_fields()
                try:
                    await self.kernel_manager.start_kernel(**kwargs)
                    k.managed = True
                except Exception as e:
                    self.log.error("Could not hydrate a manager for kernel: %s", k)
                    self.log.error(e)

    async def delete_stale_sessions(self) -> None:
        """Delete sessions that either have no kernel or no content
        found in the server.
        """
        session_rows = self.cursor.execute("SELECT * FROM session")
        mkm = self.kernel_manager
        # We need to use fetchall() here, because we delete rows,
        # which messes up the cursor if we're iterating over rows.
        for session in session_rows.fetchall():
            kid = session["kernel_id"]
            known_kids = list(mkm._kernels.keys()) + list(mkm._pending_kernels.keys())
            if kid not in known_kids:
                self.log.debug(
                    "Kernel %s found in the session_manager but "
                    "not in the kernel_manager. Deleting this session.",
                    kid,
                )
                # session = await self.get_session(kernel_id=kid)
                self.cursor.execute("DELETE FROM session WHERE kernel_id=?", (kid,))
            # TODO: There is an issue with the logic below. It isn't necessarily
            # guaranteed that the document listed in a session has been saved
            # to disk. In particular, creating a new document in JLab causes
            # issues for this logic. The session is created/saved before the
            # new document is saved. The logic below doesn't *see* the document
            # and subsequently deletes the session. There is no way (today) to
            # get a "pending" content.
            # # Check the contents manager for documents.
            # file_exists = self.contents_manager.exists(path=session["path"])
            # if not file_exists:
            #     session_id = session["session_id"]
            #     self.log.debug(
            #         f"The document path for {session_id} was not found. Deleting this session."
            #     )
            #     await self.delete_session(session_id)

    async def shutdown_kernels_without_sessions(self) -> None:
        """Shutdown 'unknown' kernels (found in kernelmanager but
        not the session manager).
        """
        for kernel_id in self.kernel_manager.list_kernel_ids():
            try:
                kernel = await self.get_session(kernel_id=kernel_id)
            except Exception:
                try:
                    kernel = self.kernel_manager.get_kernel(kernel_id)
                    if not kernel.ready.done() or kernel_id in self._pending_sessions:
                        continue
                    self.log.debug(
                        "Kernel %s found in the kernel_manager is not "
                        "found in the session database. Shutting down the kernel.",
                        kernel_id,
                    )
                    await self.kernel_manager.shutdown_kernel(kernel_id)
                # Log any failures, but don't raise exceptions.
                except Exception as err2:
                    self.log.info(err2)

    async def sync_kernels(self) -> None:
        """Synchronize the kernel manager, kernel database, and
        remote kernel service.
        """
        self._kernel_records = KernelRecordList()
        await self.fetch_kernel_records()

        self.remove_stale_kernels()
        await self.hydrate_kernel_managers()
        self.record_kernels()

    async def sync_sessions(self) -> None:
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

    async def sync_managers(self) -> None:
        """Rehydrate sessions and kernels managers from the remote
        kernel service.
        """
        self.log.debug("Synchronizing kernel records.")
        await self.sync_kernels()
        self.log.debug("Synchronizing kernel sessions.")
        await self.sync_sessions()

    async def list_sessions(self) -> list[dict[str, t.Any]]:
        """List the sessions."""
        # Run the synchronizer loop
        try:
            await self.sync_managers()
        except Exception as e:
            self.log.error(e)
        out = await super().list_sessions()
        return t.cast(t.List[t.Dict[str, t.Any]], out)

    async def _regular_syncing(self, interval: float = 5.0) -> None:
        """Start regular syncing on a defined interval."""
        while True:
            self.log.info("Synchronizer is starting another loop.")
            # Try to synchronizer. If failed, log the exception.
            try:
                await self.sync_managers()
            except Exception as err:
                self.log.error("Synchronizer failed: %s", err)
                if self.log.isEnabledFor(10):
                    self.log.exception(err)
            await asyncio.sleep(interval)

    def start_regular_syncing(self) -> asyncio.Future[t.Any]:
        """Run regular syncing in a background task."""
        return asyncio.ensure_future(self._regular_syncing(interval=self.syncing_interval))
