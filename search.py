import math
from pprint import pprint
import sys

from db import sqlite_connect


def shorten_text(text):
    if text:
        text = text.split("\n", 1)[0]
        return text if len(text) < 80 else f"{text[:80]}..."
    return text


def get_doc_count(connection, table):
    cursor = connection.cursor()
    return cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def idf(connection, table, doc_count, term):
    cursor = connection.cursor()
    row = cursor.execute(
        f"SELECT doc FROM {table}_vocab WHERE term = ?", (term,)
    ).fetchone()
    if row is None:
        return math.log(1.0 + doc_count)
    df = row[0]
    return math.log(1.0 + doc_count / df)


def filter_query(connection, table, doc_count, query, threshold=1.5):
    terms = query.lower().split()
    idfs = {term: idf(connection, table, doc_count, term) for term in terms}
    kept = [term for term, score in idfs.items() if score >= threshold]
    if not kept:
        kept = [max(idfs, key=idfs.get)]
    return " ".join(kept)


def fts5_escape(query, n=100):
    return " ".join(f'"{term}"' for term in query.split())
    # escaped = query.replace('"', '""')
    # return f'"{escaped}"'


def search_query_order(minimum_bm25, bm25, maximum_rank, rank, alpha):
    # assert bm25 * rank >= minimum_bm25 * maximum_rank
    # return bm25 * rank
    norm_bm25 = -bm25 / minimum_bm25
    norm_rank = -rank / maximum_rank
    return alpha * norm_bm25 + (1 - alpha) * norm_rank


def search_query(query, k=10, title_weight=1, text_weight=1, alpha=0.5):
    pages = []
    with sqlite_connect() as connection:
        connection.create_function("search_query_order", 5, search_query_order)
        doc_count = get_doc_count(connection, "internal_texts")
        match_titles = fts5_escape(
            filter_query(connection, "internal_pages", doc_count, query)
        )
        match_texts = fts5_escape(
            filter_query(connection, "internal_texts", doc_count, query)
        )
        cursor = connection.cursor()
        raw_pages = cursor.execute(
            """
            WITH title_candidates AS (
                SELECT p.id, p.ns, p.title, t.text,
                    ? * bm25(internal_pages_fts) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts t ON t.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts MATCH ? 
                ORDER BY bm25
            ),
            text_candidates AS (
                SELECT p.id, p.ns, p.title, t.text,
                    ? * bm25(internal_texts_fts) AS bm25, p.rank1 AS rank1 
                FROM internal_pages p
                INNER JOIN internal_texts t ON t.id = p.text_id
                INNER JOIN internal_texts_fts tfts ON tfts.rowid = t.id
                WHERE p.ns = 0 AND internal_texts_fts MATCH ? 
                ORDER BY bm25
            ),
            candidates AS (
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM text_candidates
                ORDER BY bm25 
                LIMIT ?
            ),
            redirect_candidates AS (
                SELECT 
                    COALESCE(t.id, s.id) AS id, 
                    COALESCE(t.ns, s.ns) AS ns, 
                    COALESCE(t.title, s.title) AS title, 
                    COALESCE(t.text, s.text) AS text, 
                    COALESCE(t.bm25, s.bm25) AS bm25, 
                    COALESCE(t.rank1, s.rank1) AS rank, 
                    CASE WHEN r.source_id = s.id THEN s.title ELSE NULL END AS redirect 
                FROM candidates s
                LEFT JOIN redirects r ON r.source_id = s.id
                LEFT JOIN candidates t ON t.id = r.target_id 
                ORDER BY bm25
            ),
            extrema AS (
                SELECT 
                    min(bm25) AS minimum_bm25,
                    max(rank) AS maximum_rank
                FROM redirect_candidates
            )
            SELECT redirect_candidates.*
            FROM redirect_candidates
            CROSS JOIN extrema
            -- WHERE bm25 < .5 * minimum_bm25
            ORDER BY search_query_order(minimum_bm25, bm25, maximum_rank, rank, ?)
            """,
            (title_weight, match_titles, text_weight, match_texts, 10 * k, alpha),
        ).fetchall()
        lookup = set()
        pages = []
        for page_id, ns, title, text, bm25, rank, redirect in raw_pages:
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
                        "redirect": redirect,
                    }
                )
        return match_titles, match_texts, pages[:k]


if __name__ == "__main__":
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as log_file:
            pprint(
                search_query(sys.argv[1], title_weight=1, text_weight=1, alpha=0.5),
                log_file,
            )
    elif len(sys.argv) > 1:
        pprint(search_query(sys.argv[1], title_weight=1, text_weight=1, alpha=0.5))
