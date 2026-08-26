"""
Root conftest.py — patches PG-only constructs so the test suite runs on SQLite.

1. pgvector VectorField: returns BLOB for db_type on SQLite.
2. pgvector HnswIndex: intercept at deferred_sql level.
   Django's create_model appends index.create_sql() to deferred_sql and executes
   them in __exit__. We filter out HnswIndex-generated SQL before execution.
3. BaseDatabaseSchemaEditor.add_index: also patched so explicit AddIndex migration
   operations are skipped on SQLite.
"""


def pytest_configure(config):
    try:
        from pgvector.django import VectorField, HnswIndex  # type: ignore[import-untyped]
        from django.db.backends.base.schema import BaseDatabaseSchemaEditor

        # --- VectorField: use BLOB column type on SQLite ---
        _orig_db_type = VectorField.db_type

        def _sqlite_db_type(self, conn):
            if conn.vendor == "sqlite":
                return "BLOB"
            return _orig_db_type(self, conn)

        VectorField.db_type = _sqlite_db_type

        # --- HnswIndex.create_sql: return no-op on SQLite ---
        _orig_create_sql = HnswIndex.create_sql

        def _sqlite_create_sql(self, model, schema_editor, **kwargs):
            if schema_editor.connection.vendor == "sqlite":
                return None
            return _orig_create_sql(self, model, schema_editor, **kwargs)

        HnswIndex.create_sql = _sqlite_create_sql

        # --- BaseDatabaseSchemaEditor.__exit__: strip None from deferred_sql ---
        _orig_exit = BaseDatabaseSchemaEditor.__exit__

        def _patched_exit(self, exc_type, exc_value, traceback):
            # Remove None entries that come from our HnswIndex no-op
            if self.connection.vendor == "sqlite":
                self.deferred_sql = [s for s in self.deferred_sql if s is not None]
            return _orig_exit(self, exc_type, exc_value, traceback)

        BaseDatabaseSchemaEditor.__exit__ = _patched_exit

        # --- add_index: skip explicit AddIndex migration operations ---
        _orig_add_index = BaseDatabaseSchemaEditor.add_index

        def _patched_add_index(self, model, index):
            if self.connection.vendor == "sqlite" and isinstance(index, HnswIndex):
                return
            _orig_add_index(self, model, index)

        BaseDatabaseSchemaEditor.add_index = _patched_add_index

    except ImportError:
        pass
