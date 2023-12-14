"""Kernel database management."""
from __future__ import annotations

import pathlib
import sqlite3
from pathlib import Path
from typing import Any

from traitlets import TraitError, Type, Unicode, validate
from traitlets.config.configurable import Configurable

from .kernel_records import KernelRecord


class KernelTable(Configurable):
    """An SQLite database for recorded kernels in the current server."""

    _table_name = "kerneltable"
    _connection = None
    _cursor = None
    _ignored_fields = {"alive", "managed", "recorded"}  # noqa: RUF012

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
    def _validate_database_filepath(self, proposal: dict[str, str]) -> str:
        value = proposal["value"]
        if value == ":memory:":
            return value
        path = pathlib.Path(value)
        if path.exists():
            # Verify that the database path is not a directory.
            if path.is_dir():
                msg = "`database_filepath` expected a file path, but the given path is a directory."
                raise TraitError(msg)
            # Verify that database path is an SQLite 3 Database by checking its header.
            with Path(value).open("rb") as f:
                header = f.read(100)

            if not header.startswith(b"SQLite format 3") and header != b"":
                msg = "The given file is not an SQLite database file."
                raise TraitError(msg)
        return value

    kernel_record_class = Type(KernelRecord, klass=KernelRecord)

    @property
    def cursor(self) -> sqlite3.Cursor:
        """Start a cursor and create a database called 'session'"""
        if self._cursor is None:
            self._cursor = self.connection.cursor()
            self._cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {self._table_name}
                ({', '.join(self._table_columns)})"""
            )
        return self._cursor

    @property
    def connection(self) -> sqlite3.Connection:
        """Start a database connection"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.database_filepath, isolation_level=None)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @property
    def _table_columns(self) -> set[str]:
        return set(self.kernel_record_class.fields()).difference(self._ignored_fields)

    def query(self, query_string: str, **identifiers: Any) -> None:
        """Build and execute a query."""
        if any(key in identifiers for key in self._table_columns):
            query = query_string.format(
                *list(identifiers.keys()),
                table=self._table_name,
            )
            self.cursor.execute(query, tuple(identifiers.values()))
        else:
            err_message = "A valid identifying field for a Kernel Record was not given."
            identifiers_list = [
                field
                for field in self.kernel_record_class  # type:ignore[attr-defined]
                if field.endswith("_id")
            ]
            if identifiers_list:
                err_message += f" Examples include: {identifiers_list}"
            raise Exception(err_message)

    def save(self, record: KernelRecord) -> None:
        """Save a record."""
        fields = {k: v for k, v in record.get_active_fields().items() if k in self._table_columns}
        columns = ",".join(fields.keys())
        values_tuple = tuple(fields.values())
        values = str(values_tuple) if len(values_tuple) > 1 else f"('{values_tuple[0]}')"
        self.cursor.execute(f"INSERT INTO {self._table_name} ({columns}) VALUES {values}")  # noqa: S608

    def exists(self, **identifier: Any) -> bool:
        """Check to see if the session of a given name exists"""
        record = self.kernel_record_class(**identifier)
        self.cursor.execute(
            f"SELECT * FROM {self._table_name} WHERE kernel_id='{record.kernel_id}'"  # noqa: S608
        )
        row = self.cursor.fetchone()
        if row is not None:
            return True
        return False

    def update(self, record: KernelRecord) -> None:
        """Update a record."""
        found = False
        for record_field in record.get_identifier_fields():
            record_id = getattr(record, record_field)
            if record_id and self.exists(**{record_field: record_id}):
                found = True
                break

        if not found:
            msg = (
                "No KernelRecord found in the KernelTable. "
                "If this is a new record, use the `.save` method to store "
                "the KernelRecord."
            )
            raise Exception(msg)

        # Build the query for updating columns.
        fields = {k: v for k, v in record.get_active_fields().items() if k in self._table_columns}
        updates = []
        for key, value in fields.items():
            updates.append(f"{key}='{value}'")
        update_string = ", ".join(updates)
        x = f"UPDATE {self._table_name} SET {update_string} WHERE {record_field}='{record_id}';"  # noqa: S608
        self.cursor.execute(x)

    def delete(self, **identifier: Any) -> None:
        """Delete a record."""
        self.query("DELETE FROM {table} WHERE {0}=?", **identifier)

    def row_to_record(self, row: sqlite3.Row) -> KernelRecord:
        """Convert a row to a record."""
        items = {field: row[field] for field in self._table_columns}
        return self.kernel_record_class(**items)

    def list(self) -> list[KernelRecord]:
        """List all records."""
        self.cursor.execute(f"SELECT * FROM {self._table_name}")  # noqa: S608
        rows = self.cursor.fetchall()
        return [self.row_to_record(row) for row in rows]

    def get(self, **identifier: Any) -> KernelRecord:
        """Get a record."""
        self.query("SELECT * FROM {table} WHERE {0}=?", **identifier)
        row = self.cursor.fetchone()
        if not row:
            msg = "No match was found in database."
            raise Exception(msg)
        return self.row_to_record(row)
