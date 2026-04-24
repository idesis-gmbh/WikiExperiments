import math
from pprint import pprint
import sys

from db import sqlite_connect


def shorten_text(text):
    if text:
        text = text.split("\n", 1)[0]
        return text if len(text) < 80 else f"{text[:80]}..."
    return text


def idf(doc_count, doc):
    return math.log(1.0 + doc_count / doc) 


def get_idfs(connection, table, query):
    cursor = connection.cursor()
    doc_count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    terms = query.lower().split()
    terms_placeholders = ", ".join("?" * len(terms))
    rows = cursor.execute(
        f"SELECT term, doc FROM {table}_vocab_unicode WHERE term IN ({terms_placeholders})",
        terms,
    ).fetchall()
    idfs = {row[0]: idf(doc_count, row[1]) for row in rows}
    idfs.update({term: sys.float_info.max for term in terms if term not in idfs})
    return idfs


def build_fts_query(idfs, threshold=1.5):
    kept = {term: score for term, score in idfs.items() if score >= threshold}
    if not kept: 
        assert threshold == 1.5
        threshold = max(idfs.values())
        kept = {term: score for term, score in idfs.items if score >= threshold}
    return " OR ".join(f'"{item}"' for item in kept)


def search_query_order(minimum_bm25, bm25, maximum_rank, rank, alpha):
    # assert bm25 * rank >= minimum_bm25 * maximum_rank
    # return bm25 * rank
    norm_bm25 = -bm25 / minimum_bm25
    norm_rank = -rank / maximum_rank
    return alpha * norm_bm25 + (1 - alpha) * norm_rank


def search_query(
    query, k1=100, k2=10, title_weight=1, text_weight=1, alpha=0.5
):
    pages = []
    with sqlite_connect() as connection:
        connection.create_function("search_query_order", 5, search_query_order)
        idfs = get_idfs(connection, "internal_pages", query)
        match_titles = build_fts_query(idfs)
        idfs = get_idfs(connection, "internal_texts", query)
        match_texts = build_fts_query(idfs)
        cursor = connection.cursor()
        raw_pages = cursor.execute(
            """
            WITH title_candidates AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_pages_fts_trigram) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_trigram pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts_trigram MATCH ? 
                ORDER BY bm25
            ),
            text_candidates AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_texts_fts_trigram) AS bm25, p.rank1 AS rank1 
                FROM internal_pages p
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                INNER JOIN internal_texts_fts_trigram ptfts ON ptfts.rowid = pt.id
                WHERE p.ns = 0 AND internal_texts_fts_trigram MATCH ? 
                ORDER BY bm25
            ),
            /* category_title_candidates AS (
                SELECT s.id, s.ns, s.title, st.text,
                    ? * bm25(internal_pages_fts_trigram) AS bm25, s.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_trigram pfts ON pfts.rowid = p.id
                INNER JOIN internal_links l ON l.target_id = p.id
                INNER JOIN internal_pages s ON s.id = l.source_id
                INNER JOIN internal_texts st ON st.id = s.text_id
                WHERE p.ns = 14 AND s.ns = 0 AND internal_pages_fts_trigram MATCH ? 
                ORDER BY bm25
            ), */
            candidates AS (
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM text_candidates
                -- UNION ALL
                -- SELECT id, ns, title, text, bm25, rank1
                -- FROM category_title_candidates
                ORDER BY bm25 
                LIMIT ?
            ),
            /* redirect_candidates AS (
                SELECT 
                    COALESCE(t.id, s.id) AS id, 
                    COALESCE(t.ns, s.ns) AS ns, 
                    COALESCE(t.title, s.title) AS title, 
                    s.text AS text, 
                    s.bm25 AS bm25, 
                    COALESCE(t.rank1, s.rank1) AS rank1, 
                    CASE WHEN r.source_id = s.id THEN s.title ELSE NULL END AS redirect 
                FROM candidates s
                LEFT JOIN redirects r ON r.source_id = s.id
                LEFT JOIN internal_pages t ON t.id = r.target_id 
                ORDER BY bm25
            ),
            extrema AS (
                SELECT 
                    min(bm25) AS minimum_bm25,
                    max(rank1) AS maximum_rank1
                FROM redirect_candidates
            )
            SELECT redirect_candidates.*
            FROM redirect_candidates
            CROSS JOIN extrema
            -- WHERE bm25 < .5 * minimum_bm25
            ORDER BY search_query_order(minimum_bm25, bm25, maximum_rank1, rank1, ?) */
            extrema AS (
                SELECT 
                    min(bm25) AS minimum_bm25,
                    max(rank1) AS maximum_rank1
                FROM candidates
            )
            SELECT candidates.*
            FROM candidates
            CROSS JOIN extrema
            -- WHERE bm25 < .5 * minimum_bm25
            ORDER BY search_query_order(minimum_bm25, bm25, maximum_rank1, rank1, ?)
            """,
            (
                title_weight,
                match_titles,
                text_weight,
                match_texts,
                # title_weight,
                # match_titles,
                k1,
                alpha,
            ),
        ).fetchall()
        lookup = set()
        pages = []
        # for page_id, ns, title, text, bm25, rank, redirect in raw_pages:
        for page_id, ns, title, text, bm25, rank in raw_pages:
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
                        # "redirect": redirect,
                    }
                )
        return match_titles, match_texts, pages[:k2]


if __name__ == "__main__":
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as log_file:
            pprint(
                search_query(sys.argv[1], k1=200, title_weight=2, alpha=0.8),
                log_file,
            )
    elif len(sys.argv) > 1:
        pprint(search_query(sys.argv[1], k1=200, title_weight=2, alpha=0.8))
