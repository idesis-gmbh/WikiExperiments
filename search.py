import math
from pprint import pprint
import sqlite3
import sys

from config import OLTP_DB_FILE_NAME


def shorten_text(text):
    if text:
        text = text.split("\n", 1)[0]
        return text if len(text) < 80 else f"{text[:80]}..."
    return text


def fts5_escape(query):
    return " ".join(f'"{word}"' for word in query.split())
    # escaped = query.replace('"', '""')
    # return f'"{escaped}"'


def search_term_order(score, minimum_bm25, bm25, maximum_rank, rank):
    if score == "exact":
        return minimum_bm25 * maximum_rank - 4
    # elif score == "prefix":
    #     return minimum_bm25 * maximum_rank - 3
    # elif score == "match":
    #     return minimum_bm25 * maximum_rank - 2
    # elif score == "suffix":
    #     return minimum_bm25 * maximum_rank - 1
    else: 
        assert bm25 * rank >= minimum_bm25 * maximum_rank
        return bm25 * rank


def search_term(term, k=10):
    pages = []
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        connection.create_function("search_term_order", 5, search_term_order)
        cursor = connection.cursor()
        query = fts5_escape(term)
        print(query)
        raw_pages = cursor.execute(            
            """
            WITH candidates AS (
                SELECT 
                    COALESCE(t.id, p.id) AS id, 
                    COALESCE(t.ns, p.ns) AS ns, 
                    COALESCE(t.title, p.title) AS title, 
                    COALESCE(t.text, p.text) as text,
                    bm25(internal_pages_fts, 5.0, 1.0) AS bm25, 
                    COALESCE(t.rank1, p.rank1) AS rank, 
                    CASE WHEN COALESCE(t.title, p.title) = ? THEN 'exact'
                    WHEN COALESCE(t.title, p.title) LIKE ? || ' %' THEN 'prefix'
                    WHEN COALESCE(t.title, p.title) LIKE '% ' || ? || ' %' THEN 'match' 
                    WHEN COALESCE(t.title, p.title) LIKE '% ' || ? THEN 'suffix'
                    ELSE 'fts' END AS score,
                    CASE WHEN r.source_id = p.id THEN p.title ELSE NULL END AS redirect 
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                LEFT JOIN redirects r ON r.source_id = p.id
                LEFT JOIN internal_pages t ON t.id = r.target_id
                WHERE p.ns = 0 
                AND internal_pages_fts MATCH ?
                ORDER BY score, bm25
            ),
            extrema AS (
                SELECT 
                    min(bm25) AS minimum_bm25,
                    max(rank) AS maximum_rank
                FROM candidates
            )
            SELECT candidates.*
            FROM candidates
            CROSS JOIN extrema
            WHERE score != 'fts' OR bm25 < .8 * minimum_bm25
            ORDER BY search_term_order(score, minimum_bm25, bm25, maximum_rank, rank)
            """,
            (term, term, term, term, query),
        ).fetchall()
        lookup = set()
        pages = []
        for page_id, ns, title, text, bm25, rank, score, redirect in raw_pages:
            if page_id not in lookup:
                lookup.add(page_id)
                pages.append(
                    {
                        "term": term,
                        "query": query,
                        "page_id": page_id,
                        "ns": ns,
                        "title": title,
                        "text": shorten_text(text),
                        "bm25": bm25,
                        "rank": rank,
                        "score": score,
                        "redirect": redirect,
                    }
                )
        return pages[:k]


if __name__ == "__main__":
    with open(sys.argv[1], "w", encoding="utf-8") as file:
        pprint(search_term(sys.argv[2]), file)
