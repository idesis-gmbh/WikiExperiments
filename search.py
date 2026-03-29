import math
from pprint import pprint
import sqlite3
import sys

from config import OLTP_DB_FILE_NAME


def fts5_escape(query):
    return " ".join(f'"{word}"' for word in query.split())
    # escaped = query.replace('"', '""')
    # return f'"{escaped}"'


def shorten_text(text):
    if text:
        text = text.split("\n", 1)[0]
        return text if len(text) < 80 else f"{text[:80]}..."
    return text


def search_term(term, k=10):
    pages = []
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        cursor = connection.cursor()
        pages_by_title = cursor.execute(
            """
            SELECT *
            FROM (
                SELECT p.id, p.ns, p.title, p.text,
                    bm25(internal_pages_fts, 5.0, 1.0) AS bm25, p.rank1 AS rank, 
                    CASE WHEN p.title = ? THEN 1
                    WHEN p.title LIKE ? || ' %' THEN 2
                    WHEN p.title LIKE '% ' || ? || ' %' THEN 2
                    WHEN p.title LIKE '% ' || ? THEN 2
                    ELSE NULL END AS score
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                LEFT JOIN redirects r ON r.source_id = p.id
                WHERE p.ns = 0 
                AND (p.title = ? 
                    OR p.title LIKE ? || ' %' 
                    OR p.title LIKE '% ' || ? || ' %'
                    OR p.title LIKE '% ' || ?)
                AND r.source_id IS NULL
            ) 
            ORDER BY score, bm25, rank DESC
            LIMIT ? 
            """,
            (term, term, term, term, term, term, term, term, 10 * k),
        ).fetchall()
        pages_by_redirect_title = cursor.execute(
            """
            SELECT *
            FROM (
                SELECT t.id, t.ns, t.title, t.text,
                    bm25(internal_pages_fts, 5.0, 1.0) AS bm25, t.rank1 AS rank, 
                    CASE WHEN p.title = ? THEN 1
                    WHEN p.title LIKE ? || ' %' THEN 2
                    WHEN p.title LIKE '% ' || ? || ' %' THEN 2
                    WHEN p.title LIKE '% ' || ? THEN 2
                    ELSE NULL END AS score
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                INNER JOIN redirects r ON r.source_id = p.id
                INNER JOIN internal_pages t ON t.id = r.target_id
                WHERE p.ns = 0 
                AND (p.title = ? 
                    OR p.title LIKE ? || ' %' 
                    OR p.title LIKE '% ' || ? || ' %'
                    OR p.title LIKE '% ' || ?)
            ) 
            ORDER BY score, bm25, rank DESC
            LIMIT ? 
            """,
            (term, term, term, term, term, term, term, term, 10 * k),
        ).fetchall()
        query = fts5_escape(term)
        pages_by_text = cursor.execute(
            """
            SELECT *
            FROM (
                SELECT p.id, p.ns, p.title, p.text,
                    bm25(internal_pages_fts, 5.0, 1.0) AS bm25, p.rank1 AS rank, 2 AS score
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                LEFT JOIN redirects r ON r.source_id = p.id
                WHERE p.ns = 0 
                AND internal_pages_fts MATCH ?
                AND r.source_id IS NULL
            ) 
            ORDER BY score, bm25, rank DESC
            LIMIT ? 
            """,
            (query, 10 * k),
        ).fetchall()
        pages_by_redirect_text = cursor.execute(
            """
            SELECT *
            FROM (
                SELECT t.id, t.ns, t.title, t.text,
                    bm25(internal_pages_fts, 5.0, 1.0) AS bm25, t.rank1 AS rank, 2 AS score
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                INNER JOIN redirects r ON r.source_id = p.id
                INNER JOIN internal_pages t ON t.id = r.target_id
                WHERE p.ns = 0 AND internal_pages_fts MATCH ?
            ) 
            ORDER BY score, bm25, rank DESC
            LIMIT ? 
            """,
            (query, 10 * k),
        ).fetchall()
        lookup = set()
        pages = []
        for page_id, ns, title, text, bm25, rank, score in sorted(
            pages_by_title
            + pages_by_redirect_title
            + pages_by_text
            + pages_by_redirect_text,
            key=lambda row: (row[-1], -row[-2] * row[-3]),
        ):
            if page_id not in lookup:
                lookup.add(page_id)
                pages.append(
                    {
                        "page_id": page_id,
                        "ns": ns,
                        "title": title,
                        "text": shorten_text(text),
                        "bm25": bm25,
                        "rank": rank,
                        "score": score,
                    }
                )
        return pages[:k]


if __name__ == "__main__":
    with open(sys.argv[1], "w", encoding="utf-8") as file:
        pprint(search_term(sys.argv[2]), file)
