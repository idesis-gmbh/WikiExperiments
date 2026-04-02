import csv
from pathlib import Path
import sqlite3
import time
import duckdb

from config import WIKI_NAME, OLTP_DB_FILE_NAME, OLAP_DB_FILE_NAME

DAMPING_FACTOR = 0.85
MAX_ITERATIONS = 50
CONVERGENCE_DELTA = 1e-6


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


def page_rank(connection, ns):
    cursor = connection.cursor()
    
    args = ", ".join("?"*len(ns))
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
            WHERE ns IN ({args})
        )
        WHERE ns IN ({args})""",
        (*ns, *ns),
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
            WHERE ns IN ({args})""",
            (*ns,),
        )

        cursor.execute(
            f"""
            WITH connected_page_ranks AS (
                SELECT target_id, SUM({rank1} / out_degree) AS rank 
                FROM internal_pages
                INNER JOIN internal_links ON source_id = id
                WHERE ns in ({args})
                GROUP BY target_id
            )
            UPDATE internal_pages 
            SET {rank2} = internal_pages.{rank2} + connected_page_ranks.rank
            FROM connected_page_ranks
            WHERE internal_pages.id = connected_page_ranks.target_id
            AND ns IN ({args})""",
            (*ns, *ns),
        )

        cursor.execute(
            f"""
            WITH disconnected_page_ranks AS (
                SELECT (1.0 - sum({rank2})) / COUNT(*) AS rank
                FROM internal_pages
                WHERE ns IN ({args})
            )
            UPDATE internal_pages
            SET {rank2} = internal_pages.{rank2} + disconnected_page_ranks.rank
            FROM disconnected_page_ranks
            WHERE ns IN ({args})""",
            (*ns, *ns),
        )

        cursor.execute(
            f"""
            UPDATE internal_pages
            SET {rank2} =  {1.0 - DAMPING_FACTOR} / (SELECT COUNT(*) FROM internal_pages) + 
                        {DAMPING_FACTOR} * ({rank2})
            WHERE ns IN ({args})""",
            (*ns,),
        )

        result = cursor.execute(
            f"""
            SELECT MAX(ABS({rank1} - {rank2})) AS max_delta
            FROM internal_pages
            WHERE ns IN ({args})""",
            (*ns,),
        )
        max_delta = result.fetchone()[0]
        print(f"Delta {max_delta}")
        if max_delta < CONVERGENCE_DELTA:
            cursor.execute(
                f"""
                UPDATE internal_pages
                SET {rank1} = {rank2}
                WHERE ns IN ({args})""",
                (*ns,),
            )
            break

        connection.commit()


def run_page_rank_oltp(ns):
    start = time.time()
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        page_rank(connection, ns)
    end = time.time()
    print(f"Pagerank computed: {end - start:.2f} seconds")


def create_olap_db(oltp_db_file_name, olap_db_file_name):
    with duckdb.connect(olap_db_file_name) as connection:
        connection.execute(f"""
            ATTACH '{oltp_db_file_name}' AS sqlite_db (TYPE SQLITE)""")
        connection.execute("""
            CREATE OR REPLACE TABLE internal_pages AS 
            SELECT * EXCLUDE(text_id) FROM sqlite_db.internal_pages""")
        connection.execute("""
            CREATE OR REPLACE TABLE internal_links AS 
            SELECT * FROM sqlite_db.internal_links""")
        connection.execute("""
            CREATE OR REPLACE TABLE external_domains AS 
            SELECT * FROM sqlite_db.external_domains""")
        connection.execute("""
            CREATE OR REPLACE TABLE external_pages AS 
            SELECT * FROM sqlite_db.external_pages""")
        connection.execute("""
            CREATE OR REPLACE TABLE external_links AS 
            SELECT * FROM sqlite_db.external_links""")
        connection.execute("DETACH sqlite_db")


def transfer_results(oltp_db_file_name, olap_db_file_name):
    csv_file = Path(oltp_db_file_name).parent / f"{WIKI_NAME}-ranks.csv"
    with duckdb.connect(olap_db_file_name) as connection:
        connection.execute(f"""
            COPY (
                SELECT p.id, p.rank1 + COALESCE(cp.rank1, 0), p.rank2 +  + COALESCE(cp.rank2, 0)
                FROM internal_pages p
                LEFT JOIN internal_pages cp ON cp.ns = 14 and cp.title = 'Category:' || p.title
                WHERE p.ns = 0
            ) TO '{csv_file}' (FORMAT CSV, HEADER true)""")
    with sqlite3.connect(oltp_db_file_name) as connection:
        connection.execute("""
            CREATE TEMP TABLE ranks_temporary 
            (id INTEGER, rank1 REAL NULL, rank2 REAL NULL)""")
        connection.executemany(
            "INSERT INTO ranks_temporary VALUES (?, ?, ?)", csv.reader(open(csv_file))
        )
        connection.execute("""
            UPDATE internal_pages 
            SET rank1 = temporary.rank1, rank2 = temporary.rank2
            FROM ranks_temporary temporary
            WHERE internal_pages.id = temporary.id""")


def run_page_rank_olap(ns):
    start = time.time()
    create_olap_db(OLTP_DB_FILE_NAME, OLAP_DB_FILE_NAME)
    with duckdb.connect(OLAP_DB_FILE_NAME) as connection:
        page_rank(connection, ns)
    end = time.time()
    print(f"Pagerank computed: {end - start:.2f} seconds")
    start = time.time()
    transfer_results(OLTP_DB_FILE_NAME, OLAP_DB_FILE_NAME)
    end = time.time()
    print(f"Results transferred: {end - start:.2f} seconds")


def run():
    # run_page_rank_oltp([0, 14])
    run_page_rank_olap([0, 14])


if __name__ == "__main__":
    run()
