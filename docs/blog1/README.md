# What Does Wikipedia Really Know? PageRank, SQL, and a Surprising Beetle

Wikipedia is the largest human-curated knowledge base in the world. Millions of articles, hundreds of millions of internal links — and right in the middle of it, a question that wouldn't let us go: which articles actually form the backbone of this knowledge network?

To find out, we applied PageRank to the English Wikipedia — the same algorithm Google once used to sort the web. The results were revealing. And in one place, quite unexpected.

## PageRank: Importance Through Links

PageRank was developed by Larry Page and Sergey Brin to rank web pages by their significance. The core idea is elegant: a page is important if many important pages link to it. Importance propagates through the network iteratively until the values stabilise.

Wikipedia is a natural fit for this analysis. Its internal links are set by editors, topically meaningful, and free from commercial distortions. With millions of articles, the dataset is also large enough to make computational choices genuinely matter. The idea isn't new — [Nayuki implemented a similar approach in Java](https://www.nayuki.io/page/computing-wikipedias-internal-pageranks), and [Thalhammer & Rettinger examined in an academic study](https://www.uni-trier.de/fileadmin/fb2/LDV/Rettinger/publications/Wikipedia_pagerank1.pdf) how different link types influence rankings. Our approach differs primarily in the choice of tools: pure SQL, no external graph processor, and a direct database comparison as an explicit goal.

## The Pipeline: ETL in Two Steps

Wikipedia makes its content available as compressed XML dumps. We built a pipeline that processes this dump in two sequential steps: first all pages are loaded, then internal links, external links, and redirects. Each step is internally parallelised using `ProcessPoolExecutor`. The result lands in a SQLite database — without ever fully unpacking the compressed dump. For the full English Wikipedia, that would be over 200 GB uncompressed; the pipeline streams the dump directly.

## PageRank in Pure SQL

The actual computation runs entirely in SQL — no Python loop, no external graph processor. Because PageRank is an analytically intensive workload, we copy the data from SQLite into DuckDB before running the algorithm, then transfer the results back. Each iteration executes four SQL statements: rank reset, propagation through linked pages, handling of unlinked pages, and finally the damping factor correction.

One detail we particularly like: instead of creating a new temporary table each iteration, we use a ping-pong buffer between two columns (`rank1` and `rank2`), swapping their roles at the start of each round. This ensures consistent source values within a single iteration and avoids the overhead of creating and indexing temporary tables.

The core propagation step — shown here without the namespace filter for clarity — looks like this:

```sql
WITH connected_page_ranks AS (
    SELECT target_id, SUM(rank1 / out_degree) AS rank
    FROM internal_pages
    INNER JOIN internal_links ON source_id = id
    GROUP BY target_id
)
UPDATE internal_pages
SET rank2 = internal_pages.rank2 + connected_page_ranks.rank
FROM connected_page_ranks
WHERE internal_pages.id = connected_page_ranks.target_id;
```

After around 30 iterations the algorithm converges — the maximum ranking difference between two passes falls below 1e-6.

## SQLite vs. DuckDB: A 30x Speed Difference

PageRank is an analytically intensive workload: many aggregations over large datasets, many repetitions. That makes it an informative benchmark for choosing a database engine.

We ran the same algorithm against both SQLite and DuckDB:

| Engine | Time (~30 iterations) |
|--------|----------------------|
| SQLite | ~720 seconds |
| DuckDB | ~24 seconds |

DuckDB is **roughly 30 times faster** — with numerically identical results. The database is also more than 10 times smaller, thanks to columnar storage and compression. For the full English Wikipedia, that's the difference between a run that takes hours and one that takes minutes. This aligns with what independent benchmarks show: [DuckDB dominates analytical workloads against SQLite](https://www.lukas-barth.net/blog/sqlite-duckdb-benchmark/) — the difference lies in vectorised execution and the column-oriented storage format optimised for aggregations over large datasets.

## The Results: What Wikipedia Considers Important

One design decision shapes the results significantly: which namespaces contribute rank to which. Wikipedia's internal links span article pages (NS 0) and category pages (NS 14), and naively mixing them produces a polluted ranking — infrastructure articles bubble up because thousands of extension pages cross-link back to them, swamping genuinely important content. The cleaner approach is to compute two independent PageRanks: article links flowing only to articles, category links flowing only to categories. The top articles then read like a genuine cross-section of collective human knowledge:

| Rank | Article |
|------|---------|
| 1 | United States |
| 2 | The New York Times |
| 3 | World War II |
| 4 | France |
| 5 | List of sovereign states |
| 6 | Germany |
| 7 | New York City |
| 8 | India |
| 9 | Russia |
| 10 | London |
| 11 | National Register of Historic Places |
| 12 | United Kingdom |
| 13 | Cerambycidae |
| 14 | The Guardian |
| 15 | Australia |
| 16 | U.S. state |
| 17 | Japan |
| 18 | China |
| 19 | Italy |
| 20 | English language |

Major powers, global media, historical turning points — that seems plausible. Then ranks 11 and 13:

**National Register of Historic Places. Cerambycidae.**

A federal property database and a family of beetles, sitting among world powers and major newspapers. Both are explained by the same structural quirk: Wikipedia contains hundreds of thousands of automatically generated stub articles — on individually listed historic properties, on insect species — each of which links back to its parent article. PageRank measures link structure, not relevance in the human sense — and that's precisely what makes these outliers valuable data points.

## Conclusion

This project shows what becomes possible when you treat Wikipedia as raw material for your own analysis: a large-scale ETL pipeline, SQL as a fully capable language for iterative graph algorithms, and a direct performance comparison between two database engines on a real workload.

The choice of the right technology is not an academic question — it's the difference between an experiment that runs and one that waits.

---

*Curious? The project is open source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*