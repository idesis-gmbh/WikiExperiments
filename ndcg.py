from collections import defaultdict
from itertools import groupby
import math
from pprint import pprint
import sys
from time import time

from config import K1, K2, TITLE_WEIGHT, TEXT_WEIGHT, ALPHA
from search import search_query
from db import sqlite_connect


def search_title(title):
    with sqlite_connect() as connection:
        cursor = connection.cursor()
        pages = cursor.execute(
            """
            SELECT * 
            FROM internal_pages
            WHERE ns = 0 AND title = ? 
            """,
            (title[9:-1].replace("_", " "),),
        ).fetchall()
        connection.commit()
        return bool(pages)


def dcg(qrels):
    return sum(
        rel / math.log2(rank + 1) for rank, (title, rel) in enumerate(qrels, start=1)
    )


def ndcg(items, qrels, k=10):
    actual_dcg = dcg(items[:k])
    ideal_dcg = dcg(qrels[:k])
    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


def load_qrels(prefix_key):
    qrels = defaultdict(dict)
    with open(
        "data/DBpedia-Entity/collection/v2/qrels-v2.txt", "r", encoding="utf-8"
    ) as in_file:
        for line in in_file:
            key, _, title, relevance = line.strip().split(maxsplit=3)
            if not key.startswith(prefix_key):
                continue
            found = search_title(title)
            qrels[key][title] = (int(relevance), found)
            # qrels[key][title] = (int(relevance), None)
    return qrels


def evaluate(
    qrels,
    prefix_key,
    k1=K1,
    k2=K2,
    title_weight=TITLE_WEIGHT,
    text_weight=TEXT_WEIGHT,
    alpha=ALPHA,
):
    with (
        open(
            f"logs/answers-v2_stopped-{k1}-{title_weight}-{text_weight}-{alpha}.log",
            "w",
            encoding="utf-8",
        ) as log_file,
        open(
            "data/DBpedia-Entity/collection/v2/queries-v2_stopped.txt",
            # "data/DBpedia-Entity/collection/v2/queries-v2.txt",
            "r",
            encoding="utf-8",
        ) as in_file,
    ):
        count_ndcg = 0
        sum_ndcg = 0.0
        for line in in_file:
            key, query = line.strip().split(maxsplit=1)
            if not key.startswith(prefix_key):
                continue
            print("query", key, query, file=log_file)
            resolvable_qrels = sorted(
                [
                    (title, rel)
                    for title, (rel, found) in qrels[key].items()
                    if found == True
                ],
                key=lambda row: row[1],
                reverse=True,
            )
            relevant_and_found = sum(1 for (title, rel) in resolvable_qrels if rel > 0)
            print("relevant & found", relevant_and_found, file=log_file)
            if relevant_and_found:
                match_titles, match_texts, items = search_query(
                    query,
                    k1=k1,
                    k2=k2,
                    title_weight=title_weight,
                    text_weight=text_weight,
                    alpha=alpha,
                )
                for item in items:
                    title = f"<dbpedia:{item['title'].replace(' ', '_')}>"
                    item["relevance"] = (
                        qrels[key][title] if title in qrels[key] else (0, None)
                    )
                answer_qrels = [(item["title"], item["relevance"][0]) for item in items]
                count_ndcg += 1
                this_ndcg = ndcg(answer_qrels, resolvable_qrels, k=k2)
                print("ndcg", this_ndcg, file=log_file)
                print("resolvable qrels", file=log_file)
                pprint(resolvable_qrels, log_file)
                print("answer qrels", file=log_file)
                pprint(answer_qrels, log_file)
                sum_ndcg += this_ndcg
        print("mean ndcg", sum_ndcg / count_ndcg, flush=True)


if __name__ == "__main__":
    prefix_key = "SemSearch_ES"
    # prefix_key = "SemSearch_LS"
    # prefix_key = "SemSearch"
    # prefix_key = "QALD2_te"
    # prefix_key = "QALD2_tr"
    # prefix_key = ""
    qrels = load_qrels(prefix_key)
    if len(sys.argv) == 1:
        for alpha in [0.8, 1]:
            evaluate(qrels, prefix_key, alpha=alpha)
    else:
        for k1 in [50, 100, 150]:
            for title_weight in [1, 2, 3]:
                for alpha in [0.7, 0.8, 0.9]:
                    start = time()
                    print(k1, title_weight, alpha, flush=True)
                    evaluate(
                        qrels,
                        prefix_key,
                        k1=k1,
                        title_weight=title_weight,
                        alpha=alpha,
                    )
                    end = time()
                    print(f"Evaluated: {end - start:.2f} seconds")
