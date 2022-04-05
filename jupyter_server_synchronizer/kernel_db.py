import pathlib
import sqlite3
from typing import List

from traitlets import TraitError, Type, Unicode, validate
from traitlets.config.configurable import Configurable

from .kernel_records import KernelRecord


class KernelTable(Configurable):
    """An SQLite database for recorded kernels in the current server."""

    _table_name = "kerneltable"
    _connection = None
    _cursor = None

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

    kernel_record_class = Type(KernelRecord, klass=KernelRecord)

    @property
    def cursor(self):
        """Start a cursor and create a database called 'session'"""
        if self._cursor is None:
            self._cursor = self.connection.cursor()
            self._cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {self._table_name}
                ({', '.join(self._table_columns)})"""
            )
        return self._cursor

    @property
    def connection(self):
        """Start a database connection"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.database_filepath, isolation_level=None)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @property
    def _table_columns(self):
        return set(self.kernel_record_class.get_identifier_fields())

    def query(self, query_string, **identifiers):
        """Build and execute a query."""
        if any(key in identifiers for key in self._table_columns):
            query = query_string.format(
                *list(identifiers.keys()),
                table=self._table_name,
            )
            self.cursor.execute(query, tuple(identifiers.values()))
        else:
            err_message = "A valid identifying field for a Kernel Record was not given."
            identifiers = [field for field in self.kernel_record_type if field.endswith("_id")]
            if identifiers:
                err_message += f" Examples include: {identifiers}"
            raise Exception(err_message)

    def save(self, record: KernelRecord) -> None:
        fields = record.get_active_identifiers()
        columns = ",".join(fields.keys())
        values = tuple(fields.values())
        if len(values) > 1:
            values = str(values)
        else:
            values = f"('{values[0]}')"
        self.cursor.execute(f"INSERT INTO {self._table_name} ({columns}) VALUES {values}")

    def exists(self, **identifier) -> bool:
        """Check to see if the session of a given name exists"""
        record = self.kernel_record_class(**identifier)
        self.cursor.execute(
            f"SELECT * FROM {self._table_name} WHERE kernel_id='{record.kernel_id}'"
        )
        row = self.cursor.fetchone()
        if row is not None:
            return True
        return False

    def update(self, record: KernelRecord) -> None:
        found = False
        for record_field in record.get_identifier_fields():
            record_id = getattr(record, record_field)
            if record_id and self.exists(**{record_field: record_id}):
                found = True
                break

        if not found:
            raise Exception(
                "No KernelRecord found in the KernelTable. "
                "If this is a new record, use the `.save` method to store "
                "the KernelRecord."
            )

        # Build the query for updating columns.
        values = record.get_active_identifiers()
        updates = []
        for key, value in values.items():
            updates.append(f"{key}='{value}'")
        update_string = ", ".join(updates)
        x = f"UPDATE {self._table_name} SET {update_string} WHERE {record_field}='{record_id}';"
        self.cursor.execute(x)

    def delete(self, **identifier) -> None:
        self.query("DELETE FROM {table} WHERE {0}=?", **identifier)

    def row_to_model(self, row: sqlite3.Row) -> KernelRecord:
        items = {field: row[field] for field in self.kernel_record_class.get_identifier_fields()}
        return self.kernel_record_class(**items)

    def list(self) -> List[KernelRecord]:
        self.cursor.execute(f"SELECT * FROM {self._table_name}")
        rows = self.cursor.fetchall()
        return [self.row_to_model(row) for row in rows]

    def get(self, **identifier) -> KernelRecord:
        self.query("SELECT * FROM {table} WHERE {0}=?", **identifier)
        row = self.cursor.fetchone()
        if not row:
            raise Exception("No match was found in database.")
        return self.row_to_model(row)
