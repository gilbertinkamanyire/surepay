"""
Database Compatibility Layer
Wraps psycopg2 to work with SQLite-style queries (? placeholders).
Falls back to SQLite for local development.
"""
import os
import re

USE_POSTGRES = bool(os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL'))


def _convert_query(sql):
    """Convert SQLite-style ? placeholders to PostgreSQL %s placeholders.
    Also handles some SQLite-specific syntax differences."""
    
    # Replace ? with %s for parameter placeholders
    converted = sql.replace('?', '%s')
    
    # SQLite: STRFTIME('%H', timestamp) -> PostgreSQL: to_char(timestamp, 'HH24')
    converted = converted.replace("STRFTIME('%H', timestamp)", "to_char(timestamp, 'HH24')")
    
    # SQLite: INSERT OR REPLACE -> PostgreSQL: INSERT ... ON CONFLICT ... DO UPDATE
    # For simplicity, handle the user_preferences table upserts
    converted = converted.replace('INSERT OR REPLACE INTO', 'INSERT INTO')
    
    # Handle AUTOINCREMENT -> handled in schema separately
    
    return converted


class PgCursorWrapper:
    """Wraps a psycopg2 cursor to behave like sqlite3 cursor with .fetchone()/.fetchall()"""
    
    def __init__(self, cursor, description):
        self._cursor = cursor
        self._description = description
    
    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if self._description:
            cols = [desc[0] for desc in self._description]
            return DictRow(dict(zip(cols, row)))
        return row
    
    def fetchall(self):
        rows = self._cursor.fetchall()
        if self._description:
            cols = [desc[0] for desc in self._description]
            return [DictRow(dict(zip(cols, row))) for row in rows]
        return rows
    
    @property
    def lastrowid(self):
        return getattr(self._cursor, 'lastrowid', None)


class DictRow(dict):
    """A dict subclass that supports both dict-style and index-style access, like sqlite3.Row."""
    
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)
    
    def keys(self):
        return super().keys()


class PgConnectionWrapper:
    """Wraps a psycopg2 connection to match sqlite3 connection interface."""
    
    def __init__(self, conn):
        self._conn = conn
    
    def execute(self, sql, params=None):
        """Execute a single SQL statement, converting ? to %s."""
        cursor = self._conn.cursor()
        converted_sql = _convert_query(sql)
        
        # Handle INSERT OR REPLACE by converting to upsert
        if 'INSERT INTO user_preferences' in converted_sql:
            # Convert to proper PostgreSQL upsert
            converted_sql = re.sub(
                r'INSERT INTO user_preferences \(([^)]+)\) VALUES \(([^)]+)\)',
                r'INSERT INTO user_preferences (\1) VALUES (\2) ON CONFLICT (user_id) DO UPDATE SET \1',
                converted_sql
            )
            # Fix the ON CONFLICT SET clause
            if 'ON CONFLICT (user_id) DO UPDATE SET user_id, theme' in converted_sql:
                converted_sql = converted_sql.replace(
                    'ON CONFLICT (user_id) DO UPDATE SET user_id, theme',
                    'ON CONFLICT (user_id) DO UPDATE SET theme = EXCLUDED.theme'
                )
            if 'ON CONFLICT (user_id) DO UPDATE SET user_id, bandwidth_mode' in converted_sql:
                converted_sql = converted_sql.replace(
                    'ON CONFLICT (user_id) DO UPDATE SET user_id, bandwidth_mode',
                    'ON CONFLICT (user_id) DO UPDATE SET bandwidth_mode = EXCLUDED.bandwidth_mode'
                )

        # platform_settings upserts keyed on the unique `key` column.
        if 'INSERT INTO platform_settings' in converted_sql and 'ON CONFLICT' not in converted_sql:
            converted_sql = re.sub(
                r'INSERT INTO platform_settings \(([^)]+)\) VALUES \(([^)]+)\)',
                r'INSERT INTO platform_settings (\1) VALUES (\2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
                converted_sql
            )

        try:
            if params:
                cursor.execute(converted_sql, params)
            else:
                cursor.execute(converted_sql)
        except Exception as e:
            self._conn.rollback()
            raise e
            
        return PgCursorWrapper(cursor, cursor.description)
    
    def executescript(self, sql):
        """Execute multiple SQL statements."""
        cursor = self._conn.cursor()
        # Split by semicolons and execute each
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for stmt in statements:
            converted = _convert_query(stmt)
            # Skip SQLite-specific PRAGMAs
            if converted.strip().upper().startswith('PRAGMA'):
                continue
            # Convert AUTOINCREMENT to SERIAL
            converted = converted.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
            converted = converted.replace('AUTOINCREMENT', '')
            # Convert TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            # PostgreSQL uses the same syntax, so this is fine
            try:
                cursor.execute(converted)
            except Exception as e:
                # Skip if table/index already exists
                self._conn.rollback()
                self._conn.cursor().execute("SELECT 1")  # Reset connection state
                continue
        return PgCursorWrapper(cursor, cursor.description)
    
    def commit(self):
        self._conn.commit()
    
    def close(self):
        self._conn.close()
    
    @property 
    def row_factory(self):
        return None
    
    @row_factory.setter
    def row_factory(self, value):
        pass  # Ignore - we handle row formatting ourselves


def get_postgres_db():
    """Get a PostgreSQL connection using Vercel's environment variables."""
    import psycopg2
    
    # Vercel provides these environment variables
    database_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("No POSTGRES_URL or DATABASE_URL environment variable found")
    
    # Vercel uses postgres:// but psycopg2 needs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    conn = psycopg2.connect(database_url, sslmode='require')
    return PgConnectionWrapper(conn)


def get_sqlite_db():
    """Get a SQLite connection for local development."""
    import sqlite3
    from config import Config
    
    db = sqlite3.connect(Config.DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=NORMAL")
    return db
