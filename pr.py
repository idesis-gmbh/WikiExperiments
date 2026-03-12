import sqlite3
import time
import duckdb


def dump(connection, debug=False):
    cursor = connection.cursor()

    if debug:
        result = cursor.execute(
            """
select * from internal_pages;
""",
            (),
        )
        for row in result.fetchall():
            print(row)

    result = cursor.execute(
        """
select sum(rank1), sum(rank2) 
from internal_pages;
""",
        (),
    )
    for row in result.fetchall():
        print(row)


def page_rank(connection):
    cursor = connection.cursor()

    cursor.execute(
        """
UPDATE internal_pages
SET out_degree = (
    SELECT COUNT(*)
    FROM internal_links
    WHERE internal_links.source_id = internal_pages.id
), rank1 = 1.0 / (
    SELECT COUNT(*) 
    FROM internal_pages 		
)
""",
        (),
    )

    for index in range(50):
        if index == 0:
            rank1, rank2 = "rank1", "rank2"
        else:
            rank1, rank2 = rank2, rank1
        start = time.time()

        print("iteration", index, "step 1")

        cursor.execute(
            f"""
UPDATE internal_pages
SET {rank2} = 0.0
""",
            (),
        )

        print("iteration", index, "step 2")

        cursor.execute(
            f"""
WITH connected_page_ranks AS (
	SELECT target_id, SUM({rank1} / out_degree) AS rank 
	FROM internal_pages
    INNER JOIN internal_links ON source_id = id
    GROUP BY target_id
)
UPDATE internal_pages 
SET {rank2} = internal_pages.{rank2} + connected_page_ranks.rank
FROM connected_page_ranks
WHERE internal_pages.id = connected_page_ranks.target_id;
""",
            (),
        )

        print("iteration", index, "step 3")

        cursor.execute(
            f"""
WITH disconnected_page_ranks AS (
	SELECT (1.0 - sum({rank2})) / COUNT(*) AS rank
	FROM internal_pages
)
UPDATE internal_pages
SET {rank2} = internal_pages.{rank2} + disconnected_page_ranks.rank
FROM disconnected_page_ranks
""",
            (),
        )

        print("iteration", index, "step 4")

        cursor.execute(
            f"""
UPDATE internal_pages
SET {rank2} = .15 / (SELECT COUNT(*) FROM internal_pages) + 
              .85 * ({rank2})
""",
            (),
        )

        print("iteration", index, "step 5")

        result = cursor.execute(
            f"""
SELECT MAX(ABS({rank1} - {rank2})) AS max_delta
FROM internal_pages
""",
            (),
        )
        max_delta = result.fetchone()[0]
        print("delta", max_delta)
        end = time.time()
        print(f"{end - start:.2f} seconds")
        if max_delta < 1e-6:
            cursor.execute(
                f"""
UPDATE internal_pages
SET {rank1} = {rank2}
""",
                (),
            )
            break

        connection.commit()


def run_page_rank_oltp(db_file_name):
    with sqlite3.connect(db_file_name) as connection:
        page_rank(connection)


def run_page_rank_olap(db_file_name):
    with duckdb.connect(db_file_name) as connection:
        page_rank(connection)


if __name__ == "__main__":
    # run_page_rank_oltp("data/test-oltp.db")
    # run_page_rank_olap("data/test-olap.db")
    run_page_rank_olap("data/wiki-olap.db")
