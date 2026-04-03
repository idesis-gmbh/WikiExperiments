from collections import defaultdict
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


def search_query_order(minimum_bm25, bm25, maximum_rank, rank):
    # assert bm25 * rank >= minimum_bm25 * maximum_rank
    # return bm25 * rank
    norm_bm25 = - bm25 / minimum_bm25
    norm_rank = - rank / maximum_rank
    alpha = .6
    return alpha * norm_bm25 + (1 - alpha) * norm_rank


def search_query(query, k=10):
    pages = []
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        connection.create_function("search_query_order", 4, search_query_order)
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
                    5 * bm25(internal_pages_fts) AS bm25, p.rank1 AS rank1
                FROM internal_pages p
                INNER JOIN internal_pages_fts pfts ON pfts.rowid = p.id
                INNER JOIN internal_texts t ON t.id = p.text_id
                -- WHERE p.ns = 0 AND internal_pages_fts MATCH ? 
                WHERE internal_pages_fts MATCH ? 
                ORDER BY bm25
            ),
            text_candidates AS (
                SELECT p.id, p.ns, p.title, t.text,
                    bm25(internal_texts_fts) AS bm25, p.rank1 AS rank1 
                FROM internal_pages p
                INNER JOIN internal_texts t ON t.id = p.text_id
                INNER JOIN internal_texts_fts tfts ON tfts.rowid = t.id
                -- WHERE p.ns = 0 AND internal_texts_fts MATCH ? 
                WHERE internal_texts_fts MATCH ? 
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
            ORDER BY search_query_order(minimum_bm25, bm25, maximum_rank, rank)
            """,
            (match_titles, match_texts, 10 * k),
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


def search_title(title):
    with sqlite3.connect(OLTP_DB_FILE_NAME) as connection:
        cursor = connection.cursor()
        pages = cursor.execute(
            """
            SELECT * 
            FROM internal_pages
            WHERE ns = 0 AND title = ? 
            """,
            (title[9:-1].replace("_", " "),),
        ).fetchall()
        return bool(pages)


def dcg(qrels):
    return sum(
        rel / math.log2(rank + 1)
        for rank, (title, rel) in enumerate(qrels, start=1)
        if rel > 0
    )


def ndcg(items, qrels, k=10):
    actual_dcg = dcg(items[:k])
    ideal_dcg = dcg(qrels[:k])
    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


if __name__ == "__main__":
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as log_file:
            pprint(search_query(sys.argv[1]), log_file)
    elif len(sys.argv) > 1:
        pprint(search_query(sys.argv[1]))
    else:
        qrels = defaultdict(dict)
        with open("data/DBpedia-Entity/collection/v2/qrels-v2.txt", "r", encoding="utf-8") as in_file:
            for line in in_file:
                key, _, title, relevance = line.strip().split(maxsplit=3)
                if not key.startswith("SemSearch_ES"):
                    continue
                found = search_title(title)
                qrels[key][title] = (int(relevance), found)
                # qrels[key][title] = (int(relevance), None)
        with (
            open("logs/answers-v2.log", "w", encoding="utf-8") as log_file,
            open(
                "data/DBpedia-Entity/collection/v2/queries-v2_stopped.txt", "r", encoding="utf-8"
            ) as in_file,
        ):
            k = 10
            count_ndcg = 0
            sum_ndcg = 0.0
            for line in in_file:
                answer = {}
                key, query = line.strip().split(maxsplit=1)
                if not key.startswith("SemSearch_ES"):
                    continue
                answer["key"] = key
                answer["query"] = query
                # answer["qrels"] = qrels[key]
                resolvable_qrels = sorted(
                    [
                        (title, rel)
                        for title, (rel, found) in qrels[key].items()
                        if found == True
                    ],
                    key=lambda row: row[1],
                    reverse=True,
                )
                # print(resolvable_qrels)
                answer["qrels"] = resolvable_qrels
                match_titles, match_texts, items = search_query(query, k=k)
                answer["match_titles"] = match_titles
                answer["match_texts"] = match_texts
                answer["items"] = items
                for item in answer["items"]:
                    title = f"<dbpedia:{item['title'].replace(' ', '_')}>"
                    if title in qrels[key]:
                        item["relevance"] = qrels[key][title]
                answer_qrels = sorted(
                    [
                        (item["title"], item["relevance"][0])
                        for item in answer["items"]
                        if "relevance" in item and item["relevance"][1] == True
                    ],
                    key=lambda row: row[1],
                    reverse=True,
                )
                # print(answer_qrels)
                print("query", query, file=log_file)
                print(
                    "relevant & found",
                    sum(1 for (title, rel) in resolvable_qrels if rel > 0),
                    file=log_file,
                )
                count_ndcg += 1
                this_ndcg = ndcg(answer_qrels, resolvable_qrels, k=k)
                sum_ndcg += this_ndcg
                print("ndcg", this_ndcg, file=log_file)
        print("mean ndcg", sum_ndcg / count_ndcg)
