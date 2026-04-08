# Searching Wikipedia: BM25, PageRank, and the Limits of Both

Building a search engine is easy. Building one you can trust is harder. After computing PageRank across the full Wikipedia link graph, the next question was obvious: can we use those ranks to make search results better? And once we had an answer, we needed a way to measure it.

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

We chose the trigram tokenizer over unicode61 for one reason: search quality is meaningfully better. Trigram indexing enables substring matching, so a query for "Einstein" finds "Albert Einstein" even without prefix anchoring. The trade-off is significant — the FTS index is substantially larger, and building it against the full English Wikipedia takes roughly two hours.

For anyone who doesn't need search, or who prefers a smaller database, switching to `unicode61 remove_diacritics 2` in `create_fts_tables.sql` restores fast indexing at the cost of match quality.

## Three Queries

The clearest way to understand what the engine actually does is to run it. We chose three queries that each exercise the ranking signals differently.

### relativity — a clean win

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Theory of relativity | -15.77 | 9.43e-7 |
| 2 | Relativity Media | -16.03 | 7.93e-7 |
| 3 | Special relativity | -15.48 | 6.41e-7 |
| 4 | The Meaning of Relativity | -15.49 | 4.04e-7 |
| 5 | History of special relativity | -15.90 | 1.48e-7 |

This is the engine working as intended. Theory of relativity lands at #1 with strong scores on both signals. Special relativity and the history article follow in plausible order. Relativity Media appears at #2 — a media company, not a physics concept — but its PageRank is genuinely high, and its title is an exact match. A human would rank it lower; the engine can't know that without understanding the query's intent.

### mercury — a soft failure

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Mercury Marquis | -12.63 | 1.58e-7 |
| 2 | Mercury-Atlas | -12.66 | 1.56e-7 |
| 3 | Mercury Monterey | -12.61 | 1.44e-7 |
| 4 | Mercury 7 | -12.71 | 1.42e-7 |
| 5 | List of Mercury-crossing minor planets | -12.59 | 1.16e-7 |

The planet Mercury, the chemical element, the Roman deity — none of them appear. The top ten results are dominated by Ford/Mercury automobile models and related articles. This happens because Wikipedia contains hundreds of stub articles on Mercury-branded cars, each of which matches the query term and carries modest but consistent PageRank from cross-linking within that cluster. No single article dominates; the cluster does. It is a structural artefact, not a relevance signal — and the engine has no way to distinguish the two.

### newton — a hard failure

| Rank | Title | BM25 | PageRank |
|------|-------|------|----------|
| 1 | National Register of Historic Places listings in Newton, Massachusetts | -12.80 | 1.11e-6 |
| 2 | West Newton, Massachusetts | -12.64 | 4.60e-7 |
| 3 | Newton Upper Falls | -12.58 | 1.07e-7 |
| 4 | Newton-by-the-Sea | -12.60 | 7.10e-8 |
| 5 | Religious views of Isaac Newton | -12.60 | 4.67e-8 |

Isaac Newton does not appear. The top result — a National Register of Historic Places listing for a town in Massachusetts — ranks first because thousands of NRHP list articles link to it, inflating its PageRank far beyond what its content warrants for this query. The BM25 scores across the top results are nearly identical (all around -12.6 to -12.8), so PageRank breaks the tie — and breaks it badly.

This is the clearest illustration of what PageRank actually measures: link structure, not importance in any human sense. "National Register of Historic Places listings in Newton, Massachusetts" is well-connected within a large, densely cross-linked article cluster. Isaac Newton is well-connected too — but the article is titled *Isaac Newton*, not *Newton*, so it doesn't match the trigram query as strongly, and PageRank can't compensate for what BM25 misses.

## Evaluating with nDCG

These three examples give intuition, but intuition over individual queries is unreliable. What you need is a benchmark.

We used the SemSearch_ES subset of DBpedia-Entity v2 — a keyword-oriented entity retrieval benchmark with human-annotated relevance judgements. The metric is nDCG@10: Normalised Discounted Cumulative Gain at rank 10. It rewards finding relevant documents early in the result list, and penalises burying them:

```
DCG@k = Σ rel_i / log2(i + 1)
```

Dividing by the ideal DCG gives nDCG, a value between 0 and 1. On full English Wikipedia, the engine achieves a mean nDCG@10 of **0.37**.

That number sits in honest territory. It is not a failure — 0.37 on a benchmark designed for semantic retrieval systems, using nothing but keyword matching and link structure, is a reasonable result. But the newton and mercury queries illustrate exactly where the remaining 0.63 goes: disambiguation failures, cluster inflation, and the fundamental gap between structural importance and topical relevance.

## What Would Help

Both failure modes point in the same direction. Mercury and newton are ambiguous terms where the "right" answer depends on query intent that keyword matching cannot infer. The structural fixes are well-known:

**Query expansion and entity linking** would help mercury and newton by identifying the most prominent named entity for each term and boosting it directly. **Semantic embeddings** would help by encoding query intent rather than surface terms — a dense retrieval model would place Isaac Newton far above a Massachusetts town regardless of BM25 scores. Both approaches add complexity and latency; neither is a drop-in replacement for the current architecture.

The current system's strengths — speed, interpretability, no GPU required — are real. For unambiguous entity queries it works well. For single-word common nouns with many valid referents, it doesn't, and adding a second signal won't fix what is fundamentally a disambiguation problem.

## Conclusion

Building the search engine was straightforward. The harder part was building an evaluation harness we could trust, and then being willing to run queries that expose the gaps. nDCG@10 of 0.37 on full English Wikipedia gave us a number; mercury and newton gave us an understanding of what that number means.

The most useful thing a benchmark can do is point precisely at what's broken. Ours does.

---

*The full code, including the evaluation harness, is open source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*