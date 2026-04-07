import csv
from pathlib import Path
import time

from config import (
    DAMPING_FACTOR,
    MAX_ITERATIONS,
    TOLERANCE,
    WIKI_NAME,
    OLTP_DB_FILE_NAME,
)
from db import duckdb_connect, sqlite_connect


def dump(connection, debug=False):
    """Debug utility"""
    cursor = connection.cursor()

    if debug:
        result = cursor.execute("select * from internal_pages")
        for row in result.fetchall():
            print(row)

    result = cursor.execute("""
        select sum(rank1), sum(rank2) 
        from internal_pages""")
    for row in result.fetchall():
        print(row)

    connection.commit()


def page_rank(connection, ns):
    cursor = connection.cursor()

    ns_placeholders = ", ".join("?" * len(ns))
    cursor.execute(
        f"""
        UPDATE internal_pages
        SET in_degree = (
            SELECT COUNT(*)
            FROM internal_links
            WHERE internal_links.target_id = internal_pages.id
        ) , out_degree = (
            SELECT COUNT(*)
            FROM internal_links
            WHERE internal_links.source_id = internal_pages.id
        ), rank1 = 1.0 / (
            SELECT COUNT(*) 
            FROM internal_pages
            WHERE ns IN ({ns_placeholders})
        )
        WHERE ns IN ({ns_placeholders})""",
        ns * 2,
    )

    for index in range(MAX_ITERATIONS):
        if index == 0:
            rank1, rank2 = "rank1", "rank2"
        else:
            rank1, rank2 = rank2, rank1

        print("Pagerank iteration", index)

        cursor.execute(
            f"""
            UPDATE internal_pages
            SET {rank2} = 0.0
            WHERE ns IN ({ns_placeholders})""",
            ns,
        )

        cursor.execute(
            f"""
            WITH connected_page_ranks AS (
                SELECT target_id, SUM({rank1} / out_degree) AS rank 
                FROM internal_pages
                INNER JOIN internal_links ON source_id = id
                WHERE ns in ({ns_placeholders})
                GROUP BY target_id
            )
            UPDATE internal_pages 
            SET {rank2} = internal_pages.{rank2} + connected_page_ranks.rank
            FROM connected_page_ranks
            WHERE internal_pages.id = connected_page_ranks.target_id
            AND ns IN ({ns_placeholders})""",
            ns * 2,
        )

        cursor.execute(
            f"""
            WITH disconnected_page_ranks AS (
                SELECT (1.0 - sum({rank2})) / COUNT(*) AS rank
                FROM internal_pages
                WHERE ns IN ({ns_placeholders})
            )
            UPDATE internal_pages
            SET {rank2} = internal_pages.{rank2} + disconnected_page_ranks.rank
            FROM disconnected_page_ranks
            WHERE ns IN ({ns_placeholders})""",
            ns * 2,
        )

        cursor.execute(
            f"""
            UPDATE internal_pages
            SET {rank2} =  {1.0 - DAMPING_FACTOR} / (SELECT COUNT(*) FROM internal_pages) + 
                        {DAMPING_FACTOR} * ({rank2})
            WHERE ns IN ({ns_placeholders})""",
            ns,
        )

        result = cursor.execute(
            f"""
            SELECT MAX(ABS({rank1} - {rank2})) AS tolerance
            FROM internal_pages
            WHERE ns IN ({ns_placeholders})""",
            ns,
        )
        delta = result.fetchone()[0]
        print(f"Delta {delta}")
        if delta < TOLERANCE:
            cursor.execute(
                f"""
                UPDATE internal_pages
                SET {rank1} = {rank2}
                WHERE ns IN ({ns_placeholders})""",
                ns,
            )
            break

        connection.commit()


def run_page_rank_oltp(ns):
    start = time.time()
    with sqlite_connect() as connection:
        page_rank(connection, ns)
    end = time.time()
    print(f"Pagerank computed: {end - start:.2f} seconds")


def create_olap_db(oltp_db_file_name=OLTP_DB_FILE_NAME):
    with duckdb_connect() as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            ATTACH '{oltp_db_file_name}' AS sqlite_db (TYPE SQLITE)""")
        cursor.execute("""
            CREATE OR REPLACE TABLE internal_pages AS 
            SELECT * EXCLUDE(text_id) FROM sqlite_db.internal_pages""")
        cursor.execute("""
            CREATE OR REPLACE TABLE internal_links AS 
            SELECT * FROM sqlite_db.internal_links""")
        cursor.execute("""
            CREATE OR REPLACE TABLE external_domains AS 
            SELECT * FROM sqlite_db.external_domains""")
        cursor.execute("""
            CREATE OR REPLACE TABLE external_pages AS 
            SELECT * FROM sqlite_db.external_pages""")
        cursor.execute("""
            CREATE OR REPLACE TABLE external_links AS 
            SELECT * FROM sqlite_db.external_links""")
        cursor.execute("DETACH sqlite_db")
        connection.commit()


def transfer_results(oltp_db_file_name=OLTP_DB_FILE_NAME):
    csv_file = Path(oltp_db_file_name).parent / f"{WIKI_NAME}-ranks.csv"
    with duckdb_connect() as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            COPY (
                SELECT p.id, p.rank1, p.rank2
                FROM internal_pages p
            ) TO '{csv_file}' (FORMAT CSV, HEADER true)""")
        connection.commit()
    with sqlite_connect() as connection:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TEMP TABLE ranks_temporary 
            (id INTEGER, rank1 REAL NULL, rank2 REAL NULL)""")
        rows = iter(csv.reader(open(csv_file)))
        next(rows)
        cursor.executemany("INSERT INTO ranks_temporary VALUES (?, ?, ?)", rows)
        cursor.execute("""
            UPDATE internal_pages 
            SET rank1 = temporary.rank1, rank2 = temporary.rank2
            FROM ranks_temporary temporary
            WHERE internal_pages.id = temporary.id""")
        connection.commit()


def run_page_rank_olap(ns):
    start = time.time()
    create_olap_db()
    with duckdb_connect() as connection:
        page_rank(connection, ns)
    end = time.time()
    print(f"Pagerank computed: {end - start:.2f} seconds")
    start = time.time()
    transfer_results()
    end = time.time()
    print(f"Results transferred: {end - start:.2f} seconds")


def run():
    # run_page_rank_oltp([0, 14])
    run_page_rank_olap([0, 14])


if __name__ == "__main__":
    run()
