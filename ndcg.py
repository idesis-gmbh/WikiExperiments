from collections import defaultdict
import math
import sqlite3

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


def evaluate():
    qrels = defaultdict(dict)
    with open(
        "data/DBpedia-Entity/collection/v2/qrels-v2.txt", "r", encoding="utf-8"
    ) as in_file:
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
            "data/DBpedia-Entity/collection/v2/queries-v2_stopped.txt",
            "r",
            encoding="utf-8",
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
            match_titles, match_texts, items = search_query(
                query, k=k, title_weight=1, text_weight=1, alpha=0.5
            )
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


if __name__ == "__main__":
    evaluate()
