from dataclasses import dataclass, fields
from typing import Union


class KernelRecordConflict(Exception):
    """An exception raised when trying to merge two
    kernels that have conflicting data.
    """

    pass


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
    kernel_id: Union[None, str] = None
    alive: Union[None, bool] = None
    recorded: Union[None, bool] = None
    managed: Union[None, bool] = None

    @classmethod
    def get_identifier_fields(cls):
        """The identifier keys/labels for a KernelRecord."""
        identifier_fields = []
        for field in fields(cls):
            if field.name.endswith("_id"):
                identifier_fields.append(field.name)
        return identifier_fields

    def get_identifier_values(self):
        """The values of all identifiers."""
        identifier_values = []
        for id in self.get_identifier_fields():
            if id.endswith("_id"):
                identifier_values.append(getattr(self, id))
        return identifier_values

    def get_active_identifiers(self):
        """Return a dictionary of all identifiers that are not None."""
        identifiers = {}
        for id in self.get_identifier_fields():
            val = getattr(self, id)
            if val is not None:
                identifiers[id] = val
        return identifiers

    def __eq__(self, other: "KernelRecord") -> bool:
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
                raise KernelRecordConflict(
                    "Two kernel records show some IDs are equivalent, "
                    "while others are not. Here is a list of conflicting "
                    f"IDs: {conflicts}"
                )

            return equivalence_found
        return False

    def update(self, other: "KernelRecord") -> None:
        """Updates in-place a kernel from other (only accepts positive updates"""
        if not isinstance(other, KernelRecord):
            raise TypeError("'other' must be an instance of KernelRecord.")

        if other.kernel_id and self.kernel_id and other.kernel_id != self.kernel_id:
            raise KernelRecordConflict(
                "Could not update the record from 'other' because the two records conflict."
            )

        for field in fields(self):
            if hasattr(other, field.name) and getattr(other, field.name):
                setattr(self, field.name, getattr(other, field.name))


class KernelRecordList:
    """Handy object for storing and managing a list of KernelRecords.
    When adding a record to the list, first checks if the record
    already exists. If it does, the record will be updated with
    the new information.
    """

    def __init__(self, *records):
        self._records = []
        for record in records:
            self.update(record)

    def __str__(self):
        return str(self._records)

    def __contains__(self, record: Union[KernelRecord, str]):
        """Search for records by kernel_id and session_id"""
        if isinstance(record, KernelRecord) and record in self._records:
            return True

        if isinstance(record, str):
            for r in self._records:
                if record in r.get_identifier_values():
                    return True
        return False

    def __len__(self):
        return len(self._records)

    def get(self, record: Union[KernelRecord, str]) -> KernelRecord:
        if isinstance(record, str):
            for r in self._records:
                if record in r.get_identifier_values():
                    return r
        elif isinstance(record, KernelRecord):
            for r in self._records:
                if record == r:
                    return record
        raise ValueError(f"{record} not found in KernelRecordList.")

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
