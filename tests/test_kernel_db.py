import sqlite3
from dataclasses import dataclass
from typing import Union

import pytest

from jupyter_server_synchronizer.kernel_db import KernelTable
from jupyter_server_synchronizer.kernel_records import KernelRecord


def test_database_is_created(jp_environ, jp_runtime_dir):
    path = jp_runtime_dir / "jupyter-session.db"
    table = KernelTable(database_filepath=str(path))
    con = table.connection
    assert path.exists()


def test_cursor(jp_environ):
    table = KernelTable()
    cursor = table.cursor
    assert isinstance(cursor, sqlite3.Cursor)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    out = cursor.fetchone()
    assert "kerneltable" in out


def test_save_kernelrecord(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable()
    record = KernelRecord(kernel_id=kernel_id)
    table.save(record)
    found_record = table.get(kernel_id=kernel_id)
    assert hasattr(found_record, "kernel_id") and found_record.kernel_id == kernel_id


def test_delete_kernelrecord(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable()
    record = KernelRecord(kernel_id=kernel_id)
    table.save(record)
    found_record = table.get(kernel_id=kernel_id)
    assert hasattr(found_record, "kernel_id") and found_record.kernel_id == kernel_id

    table.delete(kernel_id=kernel_id)
    with pytest.raises(Exception):
        found_record = table.get(kernel_id=kernel_id)


def test_kernelrecord_exists(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable()
    record = KernelRecord(kernel_id=kernel_id)
    table.save(record)
    assert table.exists(kernel_id=kernel_id)

    table.delete(kernel_id=kernel_id)
    assert not table.exists(kernel_id=kernel_id)


def test_list_kernelrecords(jp_environ):
    table = KernelTable()
    record1 = KernelRecord(kernel_id="kernel1")
    record2 = KernelRecord(kernel_id="kernel2")

    table.save(record1)
    table.save(record2)
    things = table.list()
    assert len(things) == 2
    assert isinstance(things[0], KernelRecord)


@dataclass(eq=False)
class CustomKernelRecord(KernelRecord):
    remote_id: Union[None, str] = None


def test_save_custom_kernelrecord(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable(kernel_record_class=CustomKernelRecord)
    record = CustomKernelRecord(kernel_id=kernel_id)
    table.save(record)
    found_record = table.get(kernel_id=kernel_id)
    assert hasattr(found_record, "kernel_id") and found_record.kernel_id == kernel_id


def test_delete_custom_kernelrecord(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable(kernel_record_class=CustomKernelRecord)
    record = CustomKernelRecord(kernel_id=kernel_id)
    table.save(record)
    found_record = table.get(kernel_id=kernel_id)
    assert hasattr(found_record, "kernel_id") and found_record.kernel_id == kernel_id

    table.delete(kernel_id=kernel_id)
    with pytest.raises(Exception):
        found_record = table.get(kernel_id=kernel_id)


def test_custom_kernelrecord_exists(jp_environ):
    kernel_id = "test-kernel-id"
    table = KernelTable(kernel_record_class=CustomKernelRecord)
    record = CustomKernelRecord(kernel_id=kernel_id)
    table.save(record)
    assert table.exists(kernel_id=kernel_id)

    table.delete(kernel_id=kernel_id)
    assert not table.exists(kernel_id=kernel_id)


def test_list_custom_kernelrecord(jp_environ):
    table = KernelTable(kernel_record_class=CustomKernelRecord)
    record1 = CustomKernelRecord(kernel_id="kernel1")
    record2 = CustomKernelRecord(kernel_id="kernel2")

    table.save(record1)
    table.save(record2)
    things = table.list()
    assert len(things) == 2
    assert isinstance(things[0], CustomKernelRecord)


def test_update_custom_kernelrecord(jp_environ):
    table = KernelTable(kernel_record_class=CustomKernelRecord)
    record1 = CustomKernelRecord(kernel_id="kernel1")
    updated_record = CustomKernelRecord(kernel_id="kernel1", remote_id="remote1")
    # Save the record
    table.save(record1)
    # Update the record
    table.update(updated_record)
    things = table.list()
    assert len(things) == 1
    record = things[0]
    assert isinstance(record, CustomKernelRecord)
    assert record.kernel_id == "kernel1"
    assert record.remote_id == "remote1"
