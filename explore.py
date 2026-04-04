from collections import deque
import duckdb
import sqlite3

from config import OLTP_DB_FILE_NAME


def shortest_path(source_title, target_title):
    print(f"\n--- Shortest path: '{source_title}' → '{target_title}' ---")
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:

        def get_id(title):
            row = connection.execute(
                "SELECT id FROM internal_pages WHERE title = ?", (title,)
            ).fetchone()
            return row[0] if row else None

        def get_title(page_id):
            row = connection.execute(
                "SELECT title FROM internal_pages WHERE id = ?", (page_id,)
            ).fetchone()
            return row[0] if row else None

        def get_neighbours(page_id):
            return [
                row[0]
                for row in connection.execute(
                    "SELECT target_id FROM internal_links WHERE source_id = ?",
                    (page_id,),
                ).fetchall()
            ]

        source_id = get_id(source_title)
        target_id = get_id(target_title)

        if not source_id:
            print(f"  Page not found: '{source_title}'")
            return
        if not target_id:
            print(f"  Page not found: '{target_title}'")
            return

        # BFS
        queue = deque([[source_id]])
        visited = {source_id}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == target_id:
                titles = [get_title(pid) for pid in path]
                print(f"  Path ({len(path) - 1} hops): " + " → ".join(titles))
                return

            for neighbour in get_neighbours(current):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(path + [neighbour])

        print("  No path found.")


def redirect_statistics():
    print("\n--- Redirect statistics ---")
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        total = connection.execute("SELECT COUNT(*) FROM internal_pages").fetchone()[0]
        redirects = connection.execute("SELECT COUNT(*) FROM redirects").fetchone()[0]
        content = total - redirects
        print(f"  Total pages:    {total:>8}")
        print(f"  Content pages:  {content:>8}  ({100 * content / total:.1f}%)")
        print(f"  Redirects:      {redirects:>8}  ({100 * redirects / total:.1f}%)")


def degree_distribution():
    print("\n--- Degree distribution ---")
    with duckdb.connect(OLTP_DB_FILE_NAME) as connection:
        for degree_column in ("in_degree", "out_degree"):
            print(f"\n  {degree_column}:")
            result = connection.execute(
                f"""
                SELECT
                    CASE
                        WHEN {degree_column} = 0   THEN '0'
                        WHEN {degree_column} < 5   THEN '1-4'
                        WHEN {degree_column} < 10  THEN '5-9'
                        WHEN {degree_column} < 50  THEN '10-49'
                        WHEN {degree_column} < 100 THEN '50-99'
                        WHEN {degree_column} < 500 THEN '100-499'
                        ELSE '500+'
                    END AS bucket,
                    COUNT(*) AS pages
                FROM internal_pages
                GROUP BY bucket
                ORDER BY MIN({degree_column})
                """
            )
            for bucket, count in result.fetchall():
                bar = "█" * min(count // 1000, 50)
                print(f"    {bucket:>8} links: {count:>8} pages  {bar}")


def top_pages_by_pagerank(n=20):
    print(f"\n--- Top {n} pages by PageRank ---")
    with duckdb.connect(OLAP_DB_FILE_NAME) as connection:
        result = connection.execute(
            f"""
            SELECT title, rank1
            FROM internal_pages
            ORDER BY rank1 DESC
            LIMIT {n}
            """
        )
        for rank, (title, score) in enumerate(result.fetchall(), 1):
            print(f"  {rank:>3}. {title:<50} {score:.6f}")


if __name__ == "__main__":
    shortest_path("Mathematics", "Adolf Hitler")
    degree_distribution()
    redirect_statistics()
    top_pages_by_pagerank()
