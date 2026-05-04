import math
from pprint import pprint
import sys

from config import (
    ALPHA,
    K1,
    K2,
    TITLE_WEIGHT_UNICODE,
    TITLE_WEIGHT_TRIGRAM,
    TEXT_WEIGHT_UNICODE,
    TEXT_WEIGHT_TRIGRAM,
)
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


def get_fts_terms(idfs, threshold=1.5):
    kept = {term: score for term, score in idfs.items() if score >= threshold}
    if not kept:
        assert threshold == 1.5
        threshold = max(idfs.values())
        kept = {term: score for term, score in idfs.items() if score >= threshold}
    return [
        term
        for term, score in sorted(kept.items(), key=lambda item: item[1], reverse=True)
    ]


def search_query_order(minimum_bm25, bm25, maximum_rank, rank, alpha):
    # assert bm25 * rank >= minimum_bm25 * maximum_rank
    # return bm25 * rank
    norm_bm25 = -bm25 / minimum_bm25
    norm_rank = -rank / maximum_rank
    return alpha * norm_bm25 + (1 - alpha) * norm_rank


def search_query_in_title(
    query,
    k1=K1,
    title_weight_unicode=TITLE_WEIGHT_UNICODE,
    title_weight_trigram=TITLE_WEIGHT_TRIGRAM,
    alpha=ALPHA,
):
    with sqlite_connect() as connection:
        connection.create_function("search_query_order", 5, search_query_order)
        cursor = connection.cursor()
        idfs = get_idfs(connection, "internal_pages", query)
        title_terms = get_fts_terms(idfs)
        raw_pages = cursor.execute(
            """
            WITH title_candidates_unicode AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_pages_fts_unicode) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_unicode pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts_unicode MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),
            title_candidates_trigram AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_pages_fts_trigram) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_trigram pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts_trigram MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),                
            candidates AS (
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates_unicode
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates_trigram
            ),
            extrema AS (
                SELECT min(bm25) AS bm25, max(rank1) AS rank1
                FROM candidates
            )
            SELECT c.*
            FROM candidates c
            CROSS JOIN extrema e
            ORDER BY search_query_order(e.bm25, c.bm25, e.rank1, c.rank1, ?)
            """,
            (
                title_weight_unicode,
                " AND ".join(f'"{title_term}"' for title_term in title_terms),
                k1,
                title_weight_trigram,
                " AND ".join(f'"{title_term}"' for title_term in title_terms),
                k1,
                alpha,
            ),
        ).fetchall()
        return raw_pages


def search_query_in_title_and_text(
    query,
    k1=K1,
    title_weight_unicode=TITLE_WEIGHT_UNICODE,
    title_weight_trigram=TITLE_WEIGHT_TRIGRAM,
    text_weight_unicode=TEXT_WEIGHT_UNICODE,
    text_weight_trigram=TEXT_WEIGHT_TRIGRAM,
    alpha=ALPHA,
):
    with sqlite_connect() as connection:
        connection.create_function("search_query_order", 5, search_query_order)
        cursor = connection.cursor()
        idfs = get_idfs(connection, "internal_pages", query)
        title_terms = get_fts_terms(idfs)
        idfs = get_idfs(connection, "internal_texts", query)
        text_terms = get_fts_terms(idfs)
        raw_pages = cursor.execute(
            """
            WITH title_candidates_unicode AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_pages_fts_unicode) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_unicode pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts_unicode MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),
            title_candidates_trigram AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_pages_fts_trigram) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts_trigram pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                WHERE p.ns = 0 AND internal_pages_fts_trigram MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),                
            text_candidates_unicode AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_texts_fts_unicode) AS bm25, p.rank1 AS rank1 
                FROM internal_pages p
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                INNER JOIN internal_texts_fts_unicode ptfts ON ptfts.rowid = pt.id
                WHERE p.ns = 0 AND internal_texts_fts_unicode MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),
            text_candidates_trigram AS (
                SELECT p.id, p.ns, p.title, pt.text,
                    ? * bm25(internal_texts_fts_trigram) AS bm25, p.rank1 AS rank1 
                FROM internal_pages p
                INNER JOIN internal_texts pt ON pt.id = p.text_id
                INNER JOIN internal_texts_fts_trigram ptfts ON ptfts.rowid = pt.id
                WHERE p.ns = 0 AND internal_texts_fts_trigram MATCH ? 
                ORDER BY bm25
                LIMIT ?
            ),
            candidates AS (
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates_unicode
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM title_candidates_trigram
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM text_candidates_unicode
                UNION ALL
                SELECT id, ns, title, text, bm25, rank1
                FROM text_candidates_trigram
            ),
            extrema AS (
                SELECT min(bm25) AS bm25, max(rank1) AS rank1
                FROM candidates
            )
            SELECT c.*
            FROM candidates c
            CROSS JOIN extrema e
            ORDER BY search_query_order(e.bm25, c.bm25, e.rank1, c.rank1, ?)
            """,
            (
                title_weight_unicode,
                " OR ".join(f'"{title_term}"' for title_term in title_terms),
                k1,
                title_weight_trigram,
                query,
                k1,
                text_weight_unicode,
                " AND ".join(f'"{text_term}"' for text_term in text_terms),
                k1,
                text_weight_trigram,
                query,
                k1,
                alpha,
            ),
        ).fetchall()
        return raw_pages


def search_query(
    query,
    interactive=True,
    k1=K1,
    k2=K2,
    title_weight_unicode=TITLE_WEIGHT_UNICODE,
    title_weight_trigram=TITLE_WEIGHT_TRIGRAM,
    text_weight_unicode=TEXT_WEIGHT_UNICODE,
    text_weight_trigram=TEXT_WEIGHT_TRIGRAM,
    alpha=ALPHA,
):
    if interactive:
        raw_pages = search_query_in_title(
            query,
            k1=k1,
            title_weight_unicode=title_weight_unicode,
            title_weight_trigram=title_weight_trigram,
            alpha=alpha,
        )
    else:
        raw_pages = search_query_in_title_and_text(
            query,
            k1=k1,
            title_weight_unicode=title_weight_unicode,
            title_weight_trigram=title_weight_trigram,
            text_weight_unicode=text_weight_unicode,
            text_weight_trigram=text_weight_trigram,
            alpha=alpha,
        )
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
                    "text": text,
                    "bm25": bm25,
                    "rank": rank,
                    # "redirect": redirect,
                }
            )
    return pages[:k2]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        results = search_query(sys.argv[1], interactive=False)
        for result in results:
            tokens = result["text"].split()
            result["text"] = " ".join(tokens[:8]) + (" ..." if len(tokens) > 8 else "")
        if len(sys.argv) > 2:
            with open(sys.argv[2], "w", encoding="utf-8") as log_file:
                pprint(results, log_file)
        else:
            pprint(results)
