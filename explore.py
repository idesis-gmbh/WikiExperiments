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
    with sqlite_connect() as connection:
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


def domain_link_stats(min_links=10, limit=100):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            SELECT
                ed.name AS domain,
                ed.tld,
                COUNT(DISTINCT el.source_id) AS citing_pages,
                AVG(ip.rank1) AS avg_citing_pagerank,
                SUM(ip.rank1) AS total_citing_pagerank
            FROM external_links el
            JOIN external_pages ep ON el.target_id = ep.id
            JOIN external_domains ed ON ep.domain_id = ed.id
            JOIN internal_pages ip ON el.source_id = ip.id
            WHERE ip.ns = 0
            GROUP BY ALL
            HAVING COUNT(DISTINCT el.source_id) >= ?
            ORDER BY total_citing_pagerank DESC
            LIMIT ?
        """,
            (min_links, limit),
        ).fetchall()
        return [
            {
                "domain": domain,
                "tld": tld,
                "citing_pages": citing_pages,
                "avg_citing_pagerank": avg_citing_pagerank,
                "total_citing_pagerank": total_citing_pagerank,
            }
            for domain, tld, citing_pages, avg_citing_pagerank, total_citing_pagerank in rows
        ]


def page_source_profile(title, min_citations=2):
    with duckdb_connect() as connection:
        rows = connection.execute(
            """
            WITH profile AS (
                SELECT
                    ep.url,
                    ed.name AS domain,
                    ed.tld,
                    COUNT(*) OVER (PARTITION BY ed.id) AS domain_citation_count
                FROM internal_pages ip
                JOIN external_links el ON el.source_id = ip.id
                JOIN external_pages ep ON el.target_id = ep.id
                JOIN external_domains ed ON ep.domain_id = ed.id
                WHERE ip.title = ? AND ip.ns = 0
            )
            SELECT * FROM profile
            WHERE domain_citation_count >= ?
            ORDER BY domain_citation_count DESC, domain        """,
            (title, min_citations),
        ).fetchall()
        return [
            {
                "url": url,
                "domain": domain,
                "tld": tld,
                "domain_citation_count": domain_citation_count,
            }
            for url, domain, tld, domain_citation_count in rows
        ]


def tld_distribution(min_citing_pages=1000):
    with duckdb_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                ed.tld,
                COUNT(DISTINCT ed.id)           AS domains,
                COUNT(DISTINCT el.source_id)    AS citing_pages,
                AVG(ip.rank1)                   AS avg_citing_pagerank,
                SUM(ip.rank1)                   AS total_citing_pagerank
            FROM external_links el
            JOIN external_pages ep ON el.target_id = ep.id
            JOIN external_domains ed ON ep.domain_id = ed.id
            JOIN internal_pages ip ON el.source_id = ip.id
            WHERE ip.ns = 0
            GROUP BY ALL
            HAVING COUNT(DISTINCT el.source_id) >= ?
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

    # pprint(shortest_path("Mathematics", "Adolf Hitler"))
    # pprint(degree_distribution())
    # pprint(redirect_statistics())
    # pprint(top_pages_by_pagerank(0))
    # pprint(top_pages_by_pagerank(14))
    # pprint(domain_link_stats())
    # pprint(page_source_profile("Mathematics"))
    pprint(tld_distribution())
