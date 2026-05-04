# Searching Wikipedia: BM25, PageRank, and the Limits of Both

Building a search engine is easy. Building one you can trust is harder. After computing PageRank across the full English Wikipedia link graph, the next question was obvious: can we use those ranks to make search results better? And once we had an answer, we needed a way to measure it.

This post covers how we built a keyword search engine on top of our Wikipedia pipeline — and what three queries taught us about where it works, and where it doesn't.

## The Architecture: Two Streams, One Ranking

The search engine runs two parallel FTS queries against SQLite: one over page titles, one over lead paragraph text. Both use SQLite's FTS5 with a trigram tokenizer, which enables substring matching at the cost of a larger index. The results are merged and re-ranked by a weighted combination of BM25 and PageRank.

BM25 measures how well a document matches the query. PageRank measures how important the document is in the link graph. Neither signal alone is sufficient: BM25 without PageRank will surface obscure pages that happen to match the query terms; PageRank without BM25 will push major articles to the top regardless of relevance. The combination rewards pages that are both a good match and well-connected.

The fusion formula normalises both signals before combining them:

```python
norm_bm25 = -bm25 / minimum_bm25
norm_rank = -rank / maximum_rank
score = alpha * norm_bm25 + (1 - alpha) * norm_rank
```

The negative signs appear because FTS5 returns BM25 as a negative number — lower (more negative) means better. Alpha controls the balance; we settled on 0.5, giving each signal equal weight.

## Stopword Filtering via IDF

Before querying, we filter out high-frequency terms using IDF scores drawn from the FTS vocabulary tables. The idea: a term that appears in nearly every document carries almost no discriminative power, so including it in the query adds noise without improving recall. The threshold is set at IDF ≥ 1.5. If all terms fall below the threshold, the highest-IDF term is kept — the query must contain something.

This is a cheap but effective substitute for a hand-curated stopword list. It adapts to the corpus rather than assuming a fixed vocabulary, and it costs nothing at query time because FTS5 already maintains vocabulary statistics.

## The Trigram Trade-off

We chose the trigram tokenizer over unicode61 because search quality is meaningfully better. Trigram indexing enables substring matching, so a query for "Einstein" finds "Albert Einstein" even without prefix anchoring. The trade-off is significant — the FTS index is substantially larger, and building it against the full English Wikipedia takes roughly two hours.

For anyone who doesn't need search, or who prefers a smaller database, switching to `unicode61 remove_diacritics 2` in `create_fts_tables.sql` restores fast indexing at the cost of match quality.

## Three Queries

The clearest way to understand what the engine actually does is to run it. We chose three queries that each exercise the ranking signals differently.

### newton — a clear win

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Isaac Newton | -20.69 | 1.37e-5 |
| 2 | Newton | -25.35 | 2.43e-8 |
| 3 | Knewton | -24.64 | 5.82e-8 |
| 4 | Enewton | -24.64 | 4.56e-8 |
| 5 | Newton-X | -23.96 | 2.87e-8 |

Isaac Newton lands at rank 1 with the best BM25 score by a clear margin and a PageRank roughly 200 times higher than any other result. The rest of the list is trigram noise — articles whose titles contain the substring "newton" — which illustrates exactly the trade-off the tokenizer introduces. The ranking handles it correctly here because the gap between Isaac Newton and everything else is large enough on both signals simultaneously.

### relativity — a mixed result

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | General relativity | -26.32 | 9.92e-7 |
| 2 | Relativity Records | -26.32 | 8.41e-7 |
| 3 | Relativity Media | -26.32 | 7.93e-7 |
| 4 | Special relativity | -26.32 | 6.41e-7 |
| 5 | Relativity | -30.72 | 2.43e-8 |
| 6 | Theory of relativity | -23.17 | 9.43e-7 |

"Theory of relativity" has the best BM25 score in the list (-23.17 vs. -26.32 for the others) and a PageRank comparable to General relativity. It still lands at rank 6. The reason: the top four results all score identically on BM25 because the trigram tokenizer matches "relativity" as a substring in each title equally well, so PageRank alone separates them — and General relativity edges out Theory of relativity on that signal. With alpha at 0.5, a BM25 advantage isn't always enough to overcome a PageRank deficit when BM25 scores are bunched together. A human would place Theory of relativity first; the engine can't infer that without understanding query intent.

### mercury — a soft failure

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Mercury Records | -22.37 | 1.23e-5 |
| 2 | Mercury | -26.86 | 2.43e-8 |
| 3 | Mercury4 | -26.12 | 4.15e-8 |
| 4 | Mercury (planet) | -22.37 | 6.39e-6 |
| 5 | Mercury-P | -25.42 | 2.78e-8 |

The planet, the chemical element, the Roman deity — none in the top five. Mercury Records takes rank 1 because it ties Mercury (planet) on BM25 but has roughly twice the PageRank. A record label outranks a planet because it is better connected in Wikipedia's link graph — not because it is the more likely referent for a one-word query. The disambiguation page sits at rank 2 with weak scores on both signals, which is arguably the worst possible outcome: it's never the right answer, and it's blocking the planet from surfacing. This is the same structural problem as before — link density standing in for relevance — just with a different culprit than the Ford/Mercury car cluster.

## Evaluating with nDCG

These three examples give intuition, but intuition over individual queries is unreliable. What you need is a benchmark.

We used the SemSearch_ES subset of DBpedia-Entity v2 — a keyword-oriented entity retrieval benchmark with human-annotated relevance judgements. The metric is nDCG@10: Normalised Discounted Cumulative Gain at rank 10. It rewards finding relevant documents early in the result list, and penalises burying them:

```
DCG@k = Σ rel_i / log2(i + 1)
```

Dividing by the ideal DCG gives nDCG, a value between 0 and 1. On the full English Wikipedia, the engine achieves a mean nDCG@10 of **0.455**.

To put that in context, the DBpedia-Entity v2 leaderboard (available at [iai-group.github.io/DBpedia-Entity](https://iai-group.github.io/DBpedia-Entity/)) includes a range of retrieval models evaluated on the same benchmark. Plain BM25 scores 0.2497 on SemSearch_ES. The stronger models — language model variants with entity linking and field-weighted scoring — reach into the 0.62-0.65 range. Our result sits well above the BM25 baseline and below the serious retrieval models, which is exactly where you'd expect a system that adds only link structure on top of keyword matching, with no training data and no semantic understanding.

The newton and mercury queries illustrate precisely where the remaining gap sits: disambiguation failures and the fundamental mismatch between structural importance and topical relevance.

## What Would Help

Both failure modes point in the same direction. Mercury and relativity are queries where the "right" answer depends on intent that keyword matching cannot infer. The structural fixes are well-known:

**Query expansion and entity linking** would help mercury by identifying the most prominent named entity and boosting it directly — this is exactly what the ELR variants on the leaderboard implement, and their gains over the base models are consistent. **Semantic embeddings** would help by encoding query intent rather than surface terms — a dense retrieval model would place Mercury (planet) above a record label regardless of PageRank. Both approaches add complexity and latency; neither is a drop-in replacement for the current architecture.

The current system's strengths — speed, interpretability, no GPU required — are real. For unambiguous entity queries like newton it works well. For single-word terms with many valid referents, it doesn't, and adding a second signal won't fix what is fundamentally a disambiguation problem.

## Conclusion

Building the search engine was straightforward. The harder part was building an evaluation harness we could trust, and then being willing to run queries that expose the gaps. nDCG@10 of 0.455 on the full English Wikipedia gave us a number; mercury and relativity gave us an understanding of what that number means.

The most useful thing a benchmark can do is point precisely at what's broken. Ours does.

---

*The full code, including the evaluation harness, is open source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*
