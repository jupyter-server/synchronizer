"""Kernel records management."""
from __future__ import annotations

from dataclasses import dataclass, fields

from jupyter_client.manager import KernelManager


class KernelRecordConflict(Exception):
    """An exception raised when trying to merge two
    kernels that have conflicting data.
    """


@dataclass
class KernelRecord:
    """A dataclass that keeps a record of kernels maintained
    by Jupyter Server's synchronizer.

    Two records are considered equivalent if their unique identifiers
     are equal. In this case, calling
    `.update(...)` will merge the data of two records
    """

    # A Kernel record should have at least one field
    # that ends with `_id` in its keyname.
    kernel_id: None | str = None
    kernel_name: None | str = None
    alive: None | bool = None
    recorded: None | bool = None
    managed: None | bool = None

    @classmethod
    def fields(cls) -> list[str]:
        """Get the fields."""
        return [f.name for f in fields(cls)]

    @classmethod
    def from_manager(cls, manager: KernelManager) -> KernelRecord:
        """Create a kernel from a KernelManager."""
        record = cls()
        # Look for the record fields as attributes the kernel manager
        # and make the values match.
        for field in cls.get_identifier_fields():
            setattr(record, field, getattr(manager, field, None))
        record.kernel_name = manager.kernel_name
        record.managed = True
        return record

    @classmethod
    def get_identifier_fields(cls) -> list[str]:
        """The identifier keys/labels for a KernelRecord."""
        identifier_fields: list[str] = []
        for field in fields(cls):
            if field.name.endswith("_id"):
                identifier_fields.append(field.name)
        return identifier_fields

    def get_identifier_values(self) -> list[str | None]:
        """The values of all identifiers."""
        identifier_values: list[str | None] = []
        for id_ in self.get_identifier_fields():
            if id_.endswith("_id"):
                identifier_values.append(getattr(self, id_))
        return identifier_values

    def get_active_identifiers(self) -> dict[str, str]:
        """Return a dictionary of all identifiers that are not None."""
        identifiers: dict[str, str] = {}
        for id_ in self.get_identifier_fields():
            val = getattr(self, id_)
            if val is not None:
                identifiers[id_] = val
        return identifiers

    def get_active_fields(self) -> dict[str, str]:
        """Get a list of all fields that are not None"""
        items: dict[str, str] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if value:
                items[field.name] = value
        return items

    def __eq__(self, other: object) -> bool:
        """Two kernel records are equivalent if *any* of their
        unique identifiers (keys ending in `_id`) are equal.
        """
        if isinstance(other, KernelRecord):
            current_ids = self.get_active_identifiers()
            incoming_ids = other.get_active_identifiers()

            equivalence_found = False
            conflicts = []

            for field, current_id_value in current_ids.items():
                other_id_value = incoming_ids.get(field, None)
                if other_id_value and other_id_value == current_id_value:
                    equivalence_found = True
                if other_id_value and other_id_value != current_id_value:
                    conflicts.append(field)

            if equivalence_found and conflicts:
                msg = (
                    "Two kernel records show some IDs are equivalent, "
                    "while others are not. Here is a list of conflicting "
                    f"IDs: {conflicts}"
                )
                raise KernelRecordConflict(msg)

            return equivalence_found
        return False

    def update(self, other: object) -> None:
        """Updates in-place a kernel from other (only accepts positive updates"""
        if not isinstance(other, KernelRecord):
            msg = "'other' must be an instance of KernelRecord."
            raise TypeError(msg)

        if other.kernel_id and self.kernel_id and other.kernel_id != self.kernel_id:
            msg = "Could not update the record from 'other' because the two records conflict."
            raise KernelRecordConflict(msg)

        for field in fields(self):
            if hasattr(other, field.name) and getattr(other, field.name):
                setattr(self, field.name, getattr(other, field.name))


class KernelRecordList:
    """Handy object for storing and managing a list of KernelRecords.
    When adding a record to the list, first checks if the record
    already exists. If it does, the record will be updated with
    the new information.
    """

    def __init__(self, *records: KernelRecord) -> None:
        """Initialize the record list."""
        self._records: list[KernelRecord] = []
        for record in records:
            self.update(record)

    def __str__(self) -> str:
        """Str repr of the record list."""
        return str(self._records)

    def __contains__(self, record: KernelRecord | str) -> bool:
        """Search for records by kernel_id and session_id"""
        if isinstance(record, KernelRecord) and record in self._records:
            return True

        if isinstance(record, str):
            for r in self._records:
                if record in r.get_identifier_values():
                    return True
        return False

    def __len__(self) -> int:
        """Length of the record list."""
        return len(self._records)

    def get(self, record: KernelRecord | str) -> KernelRecord:
        """get a record."""
        if isinstance(record, str):
            for r in self._records:
                if record in r.get_identifier_values():
                    return r
        elif isinstance(record, KernelRecord):
            for r in self._records:
                if record == r:
                    return record
        msg = f"{record} not found in KernelRecordList."
        raise ValueError(msg)

    def update(self, record: KernelRecord) -> None:
        """Update a record in-place or append it if not in the list."""
        try:
            idx = self._records.index(record)
            self._records[idx].update(record)
        except ValueError:
            self._records.append(record)

    def remove(self, record: KernelRecord) -> None:
        """Remove a record if its found in the list. If it's not found,
        do nothing.
        """
        if record in self._records:
            self._records.remove(record)
