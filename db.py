from contextlib import contextmanager
import sqlite3

import duckdb

from config import OLAP_DB_FILE_NAME, OLTP_DB_FILE_NAME


@contextmanager
def sqlite_connect(db_file=OLTP_DB_FILE_NAME):
    connection = sqlite3.connect(db_file)
    connection.execute("PRAGMA journal_mode = wal")
    connection.execute("PRAGMA cache_size = -4000000")
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def duckdb_connect(db_file=OLAP_DB_FILE_NAME):
    connection = duckdb.connect(db_file)
    try:
        yield connection
    finally:
        connection.close()
