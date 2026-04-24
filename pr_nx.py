from time import time
import networkx as nx
from config import DAMPING_FACTOR, MAX_ITERATIONS, TOLERANCE
from db import sqlite_connect


def page_rank_nx(connection, ns):
    cursor = connection.cursor()
    ns_placeholders = ",".join("?" * len(ns))
    rows = cursor.execute(
        f"SELECT id FROM internal_pages WHERE ns IN ({ns_placeholders})",
        ns,
    ).fetchall()
    G = nx.DiGraph()
    G.add_nodes_from(row[0] for row in rows)
    rows = cursor.execute(
        f"""
        SELECT l.source_id, l.target_id
        FROM internal_links l
        JOIN internal_pages s ON s.id = l.source_id AND s.ns IN ({ns_placeholders})
        JOIN internal_pages t ON t.id = l.target_id AND t.ns IN ({ns_placeholders})
        """,
        ns * 2,
    ).fetchall()
    G.add_edges_from(rows)
    ranks = nx.pagerank(G, alpha=DAMPING_FACTOR, tol=TOLERANCE, max_iter=MAX_ITERATIONS)
    cursor.executemany(
        "UPDATE internal_pages SET rank1 = ?, rank2 = ? WHERE id = ?",
        [(value, value, key) for key, value in ranks.items()],
    )
    connection.commit()


def run_page_rank_nx(nss):
    start = time()
    with sqlite_connect() as connection:
        for ns in nss:
            page_rank_nx(connection, [ns])
    end = time()
    print(f"Pagerank computed: {end - start:.2f} seconds")


if __name__ == "__main__":
    run_page_rank_nx([0, 14])
