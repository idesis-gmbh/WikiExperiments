from collections import defaultdict
from itertools import groupby
import math
from pprint import pprint
import sys
from time import time

from config import (
    K1,
    K2,
    TITLE_WEIGHT_UNICODE,
    TITLE_WEIGHT_TRIGRAM,
    TEXT_WEIGHT_UNICODE,
    TEXT_WEIGHT_TRIGRAM,
    ALPHA,
)
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
    return qrels


def evaluate(
    qrels,
    prefix_key,
    interactive=False,
    k1=K1,
    k2=K2,
    title_weight_unicode=TITLE_WEIGHT_UNICODE,
    title_weight_trigram=TITLE_WEIGHT_TRIGRAM,
    text_weight_unicode=TEXT_WEIGHT_UNICODE,
    text_weight_trigram=TEXT_WEIGHT_TRIGRAM,
    alpha=ALPHA,
):
    with (
        open(
            f"logs/answers-v2_stopped-{k1}-{title_weight_unicode}-{title_weight_trigram}-{text_weight_unicode}-{text_weight_trigram}-{alpha}.log",
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
        count_ndcg, sum_pessimistic_ndcg, sum_optimistic_ndcg = 0, 0.0, 0.0
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
                start = time()
                items = search_query(
                    query,
                    interactive=interactive,
                    k1=k1,
                    k2=k2,
                    title_weight_unicode=title_weight_unicode,
                    title_weight_trigram=title_weight_trigram,
                    text_weight_unicode=text_weight_unicode,
                    text_weight_trigram=text_weight_trigram,
                    alpha=alpha,
                )
                end = time()
                print(f"Searched: {end - start:.2f} seconds", file=log_file)
                for item in items:
                    title = f"<dbpedia:{item['title'].replace(' ', '_')}>"
                    item["relevance"] = (
                        qrels[key][title] if title in qrels[key] else (0, None)
                    )
                pessimistic_answer_qrels = [
                    (item["title"], item["relevance"][0]) for item in items
                ]
                optimistic_answer_qrels = [
                    (item["title"], item["relevance"][0])
                    for item in items
                    if item["relevance"][1] is not None
                ]
                count_ndcg += 1
                # if count_ndcg > 10:
                #    break
                pessimistic_ndcg = ndcg(
                    pessimistic_answer_qrels, resolvable_qrels, k=k2
                )
                optimistic_ndcg = ndcg(optimistic_answer_qrels, resolvable_qrels, k=k2)
                print("ndcg", pessimistic_ndcg, optimistic_ndcg, file=log_file)
                print("resolvable qrels", file=log_file)
                pprint(resolvable_qrels, log_file)
                print("pessimistic answer qrels", file=log_file)
                pprint(pessimistic_answer_qrels, log_file)
                print("optimistic answer qrels", file=log_file)
                pprint(optimistic_answer_qrels, log_file)
                sum_pessimistic_ndcg += pessimistic_ndcg
                sum_optimistic_ndcg += optimistic_ndcg
        print(
            "mean ndcg",
            sum_pessimistic_ndcg / count_ndcg,
            sum_optimistic_ndcg / count_ndcg,
            flush=True,
        )


if __name__ == "__main__":
    prefix_key = "SemSearch_ES"
    # prefix_key = "SemSearch_LS"
    # prefix_key = "SemSearch"
    # prefix_key = "QALD2_te"
    # prefix_key = "QALD2_tr"
    # prefix_key = ""
    qrels = load_qrels(prefix_key)
    if len(sys.argv) == 1:
        evaluate(qrels, prefix_key, interactive=False)
    else:
        for k1 in [50, 100, 150]:
            # for k1 in [50]:
            for title_weight in [1, 2, 3]:
                # for title_weight in [2]:
                for text_weight in [1, 2, 3]:
                    # for text_weight in [1]:
                    for alpha in [0.7, 0.8, 0.9]:
                        # for alpha in [0.8]:
                        start = time()
                        print(k1, title_weight, text_weight, alpha, flush=True)
                        evaluate(
                            qrels,
                            prefix_key,
                            interactive=False,
                            k1=k1,
                            title_weight_unicode=title_weight,
                            title_weight_trigram=title_weight,
                            text_weight_unicode=text_weight,
                            text_weight_trigram=text_weight,
                            alpha=alpha,
                        )
                        end = time()
                        print(f"Evaluated: {end - start:.2f} seconds")
