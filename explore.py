from collections import deque
from db import duckdb_connect, sqlite_connect


def shortest_path(source_title, target_title):
    with sqlite_connect() as connection:

        def get_id(title):
            row = connection.execute(
                "SELECT id FROM internal_pages WHERE ns = 0 AND title = ?", (title,)
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
            return {"error": f"Page not found: '{source_title}'"}
        if not target_id:
            return {"error": f"Page not found: '{target_title}'"}

        queue = deque([[source_id]])
        visited = {source_id}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == target_id:
                return {
                    "path": [get_title(pid) for pid in path],
                    "hops": len(path) - 1,
                }

            for neighbour in get_neighbours(current):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(path + [neighbour])

        return {"error": "No path found."}


def redirect_statistics():
    with duckdb_connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM internal_pages").fetchone()[0]
        content_and_redirects = connection.execute(
            "SELECT COUNT(*) FROM internal_pages WHERE ns = 0"
        ).fetchone()[0]
        categories = connection.execute(
            "SELECT COUNT(*) FROM internal_pages WHERE ns = 14"
        ).fetchone()[0]
        redirects = connection.execute("SELECT COUNT(*) FROM redirects").fetchone()[0]
        content = content_and_redirects - redirects
        return {
            "total": total,
            "content": content,
            "categories": categories,
            "redirects": redirects,
        }


def degree_distribution():
    with duckdb_connect() as connection:
        result = {}
        for degree_column in ("in_degree", "out_degree"):
            rows = connection.execute(
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
                WHERE ns = 0
                GROUP BY bucket
                ORDER BY MIN({degree_column})
                """
            ).fetchall()
            result[degree_column] = [
                {"bucket": bucket, "pages": pages} for bucket, pages in rows
            ]
        return result


def top_pages_by_pagerank(ns, limit=100):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            SELECT title, rank1
            FROM internal_pages
            WHERE ns = ?
            ORDER BY rank1 DESC
            LIMIT ?
            """,
            (ns, limit),
        ).fetchall()
        return [
            {"rank": i, "title": title, "score": score}
            for i, (title, score) in enumerate(rows, 1)
        ]


def domain_authority(min_citing_pages=10, limit=100):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM external_domain_authority
            WHERE citing_pages >= ?
            ORDER BY total_citing_pagerank DESC
            LIMIT ?
        """,
            (min_citing_pages, limit),
        ).fetchall()
        return [
            {
                "domain": name,
                "tld": tld,
                "citing_pages": citing_pages,
                "avg_citing_pagerank": avg_citing_pagerank,
                "total_citing_pagerank": total_citing_pagerank,
            }
            for domain_id, name, tld, citing_pages, avg_citing_pagerank, total_citing_pagerank in rows
        ]


def page_source_profile(title, min_citations=1):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            SELECT * 
            FROM internal_page_profile
            WHERE ns = 0 AND title = ? AND domain_citation_count >= ?
            ORDER BY domain_citation_count DESC, domain
        """,
            (title, min_citations),
        ).fetchall()
        return [
            {
                "url": url,
                "domain": domain,
                "tld": tld,
                "domain_citation_count": domain_citation_count,
            }
            for page_id, ns, title, url, domain, tld, domain_citation_count in rows
        ]


def tld_authority(min_citing_pages=1000):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM tld_authority
            WHERE citing_pages >= ?
            ORDER BY total_citing_pagerank DESC
        """,
            (min_citing_pages,),
        ).fetchall()
        return [
            {
                "tld": tld,
                "domains": domains,
                "citing_pages": citing_pages,
                "avg_citing_pagerank": avg_citing_pagerank,
                "total_citing_pagerank": total_citing_pagerank,
            }
            for tld, domains, citing_pages, avg_citing_pagerank, total_citing_pagerank in rows
        ]


if __name__ == "__main__":
    from pprint import pprint

    pprint(shortest_path("Mathematics", "Adolf Hitler"))
    pprint(degree_distribution())
    pprint(redirect_statistics())
    pprint(top_pages_by_pagerank(0))
    pprint(top_pages_by_pagerank(14))
    pprint(domain_authority())
    pprint(page_source_profile("Mathematics"))
    pprint(tld_authority())
