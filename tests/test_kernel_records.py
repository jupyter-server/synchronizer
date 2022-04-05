from dataclasses import dataclass
from typing import Union

import pytest

from jupyter_server_synchronizer.kernel_records import (
    KernelRecord,
    KernelRecordConflict,
    KernelRecordList,
)


def test_kernel_record():
    assert KernelRecord.get_identifier_fields() == ["kernel_id"]

    record1 = KernelRecord(kernel_id="kernel1")

    assert record1.get_identifier_values() == ["kernel1"]


def test_kernel_record_equals():
    record0 = KernelRecord(kernel_id="kernel1")
    record1 = KernelRecord(kernel_id="kernel2")
    record2 = KernelRecord(kernel_id="kernel1", alive=True)
    record3 = KernelRecord(kernel_id="kernel2", alive=True)

    assert record0 != record1
    assert record0 == record2
    assert record0 != record3


def test_kernel_record_update():
    record = KernelRecord(kernel_id="kernel1")
    record_update = KernelRecord(kernel_id="kernel1", alive=True)
    record_update2 = KernelRecord(kernel_id="kernel1", recorded=True)

    record.update(record_update)
    assert record.alive

    record.update(record_update2)
    assert record.recorded


def test_kernel_record_list():
    records = KernelRecordList()
    r = KernelRecord(kernel_id="kernel1")
    records.update(r)
    assert r in records
    assert "kernel1" in records
    assert len(records) == 1

    # Test .get()
    r_ = records.get(r)
    assert r == r_
    r_ = records.get(r.kernel_id)
    assert r == r_

    with pytest.raises(ValueError):
        records.get("badkernel")

    r_update = KernelRecord(kernel_id="kernel1", alive=True)
    records.update(r_update)
    assert len(records) == 1
    assert "kernel1" in records
    assert records.get("kernel1").alive

    r2 = KernelRecord(kernel_id="kernel2")
    records.update(r2)
    assert r2 in records
    assert len(records) == 2

    records.remove(r2)
    assert r2 not in records
    assert len(records) == 1


@dataclass(eq=False)
class CustomKernelRecord(KernelRecord):
    remote_id: Union[None, str] = None


def test_custom_kernel_record():
    assert CustomKernelRecord.get_identifier_fields() == ["kernel_id", "remote_id"]


def test_custom_kernel_record_equals():
    record0 = CustomKernelRecord(kernel_id="kernel1")
    record1 = CustomKernelRecord(remote_id="remote1")
    record2 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel1")
    record3 = CustomKernelRecord(remote_id="remote2", kernel_id="kernel1")
    record4 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel2")
    record5 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel1")

    assert record0 == record2
    assert record1 == record2
    assert record3 != record4
    assert record1 != record3
    assert record3 != record4
    assert record2 == record5

    with pytest.raises(KernelRecordConflict):
        assert record2 == record3

    with pytest.raises(KernelRecordConflict):
        assert record2 == record4


def test_custom_kernel_record_update():
    record1 = CustomKernelRecord(remote_id="remote1")
    record2 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel1")
    record1.update(record2)
    assert record1.kernel_id == "kernel1"

    record1 = CustomKernelRecord(remote_id="remote1")
    record2 = CustomKernelRecord(kernel_id="kernel1")
    record1.update(record2)
    assert record1.kernel_id == "kernel1"

    record1 = CustomKernelRecord(kernel_id="kernel1")
    record2 = CustomKernelRecord(remote_id="remote1")
    record1.update(record2)
    assert record1.remote_id == "remote1"

    record1 = CustomKernelRecord(kernel_id="kernel1")
    record2 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel1")
    record1.update(record2)
    assert record1.remote_id == "remote1"

    record1 = CustomKernelRecord(kernel_id="kernel1")
    record2 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel2")
    with pytest.raises(KernelRecordConflict):
        record1.update(record2)

    record1 = CustomKernelRecord(kernel_id="kernel1", remote_id="remote1")
    record2 = CustomKernelRecord(kernel_id="kernel2")
    with pytest.raises(KernelRecordConflict):
        record1.update(record2)

    record1 = CustomKernelRecord(kernel_id="kernel1", remote_id="remote1")
    record2 = CustomKernelRecord(kernel_id="kernel2", remote_id="remote1")
    with pytest.raises(KernelRecordConflict):
        record1.update(record2)

    record1 = CustomKernelRecord(remote_id="remote1", kernel_id="kernel1")
    record2 = CustomKernelRecord(remote_id="remote2", kernel_id="kernel1")
    record1.update(record2)
    assert record1.remote_id == "remote2"


def test_kernel_record_list_of_custom_records():
    records = KernelRecordList()
    r = CustomKernelRecord(kernel_id="kernel1")
    records.update(r)
    assert r in records
    assert "kernel1" in records
    assert len(records) == 1

    # Test .get()
    r_ = records.get(r)
    assert r == r_
    r_ = records.get(r.kernel_id)
    assert r == r_

    with pytest.raises(ValueError):
        records.get("badkernel")

    r_update = CustomKernelRecord(kernel_id="kernel1", remote_id="remote1")
    records.update(r_update)
    assert len(records) == 1
    assert "remote1" in records

    r2 = CustomKernelRecord(kernel_id="kernel2")
    records.update(r2)
    assert r2 in records
    assert len(records) == 2

    records.remove(r2)
    assert r2 not in records
    assert len(records) == 1
