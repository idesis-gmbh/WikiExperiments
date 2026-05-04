# Wikipedia durchsuchen: BM25, PageRank und die Grenzen von beidem

Eine Suchmaschine zu bauen ist einfach. Eine zu bauen, der man vertrauen kann, ist schwerer. Nach der Berechnung von PageRank über den gesamten Linkgraphen der englischen Wikipedia lag die nächste Frage auf der Hand: Lassen sich diese Ränge nutzen, um Suchergebnisse zu verbessern? Und sobald wir eine Antwort hatten, brauchten wir eine Möglichkeit, sie zu messen.

Dieser Beitrag beschreibt, wie wir eine Keyword-Suchmaschine auf unserer Wikipedia-Pipeline aufgebaut haben — und was drei Suchanfragen über ihre Stärken und Grenzen verraten.

## Die Architektur: Zwei Streams, ein Ranking

Die Suchmaschine führt FTS-Anfragen gegen SQLite über zwei Felder aus — Seitentitel und Einleitungstext — und verwendet dabei zwei Tokenizer parallel: unicode61 für Standard-Term-Matching und Trigramm für Teilstring-Suche. Die vier Kandidatenmengen werden zusammengeführt und nach einer gewichteten Kombination aus BM25 und PageRank neu geordnet.

BM25 misst, wie gut ein Dokument zur Anfrage passt. PageRank misst, wie wichtig das Dokument im Linkgraphen ist. Kein Signal allein reicht aus: BM25 ohne PageRank liefert obskure Seiten, die zufällig die Suchbegriffe enthalten; PageRank ohne BM25 schiebt bedeutende Artikel nach oben, unabhängig von ihrer Relevanz für die Anfrage. Die Kombination belohnt Seiten, die sowohl gut zur Anfrage passen als auch gut vernetzt sind.

Die Fusionsformel normalisiert beide Signale vor der Kombination:

```python
norm_bm25 = -bm25 / minimum_bm25
norm_rank = -rank / maximum_rank
score = alpha * norm_bm25 + (1 - alpha) * norm_rank
```

Die negativen Vorzeichen entstehen, weil FTS5 BM25 als negative Zahl zurückgibt — kleiner (negativer) bedeutet besser. Alpha steuert die Balance; wir verwenden 0,8, womit BM25 stärker gewichtet wird als PageRank. Der Wert wurde per Grid-Search über [0,7; 0,8; 0,9] im Rahmen der Evaluation ermittelt.

## Stoppwort-Filterung via IDF

Vor der eigentlichen Anfrage filtern wir hochfrequente Begriffe anhand von IDF-Werten aus den FTS-Vokabular-Tabellen heraus. Der Gedanke: Ein Begriff, der in fast jedem Dokument vorkommt, trägt kaum zur Unterscheidung bei — seine Aufnahme in die Anfrage erzeugt Rauschen ohne Gewinn. Der Schwellenwert liegt bei IDF ≥ 1,5. Wenn alle Begriffe darunter fallen, wird der Begriff mit dem höchsten IDF-Wert behalten — die Anfrage muss etwas enthalten.

Das ist ein günstiger, aber wirksamer Ersatz für eine handgepflegte Stoppwortliste. Sie passt sich dem Korpus an, statt ein festes Vokabular vorauszusetzen, und verursacht zur Anfragezeit keinen Mehraufwand, da FTS5 die Vokabularstatistiken bereits vorhält.

## Der Trigramm-Kompromiss

Wir betreiben den Trigramm- und den unicode61-Tokenizer parallel. Trigramm-Indexierung ermöglicht Teilstring-Suche: Eine Anfrage nach "Einstein" findet "Albert Einstein" auch ohne Präfix-Anker, und Tippfehler werden robuster behandelt. Unicode61 übernimmt das Standard-Term-Matching effizienter. Der Trigramm-Index ist deutlich größer, und sein Aufbau gegen die vollständige englische Wikipedia dauert rund zwei Stunden — aber die Kombination beider Tokenizer verbessert die Suchqualität messbar gegenüber jedem einzelnen.

Wer keine Suche benötigt oder einen kleineren Index bevorzugt, kann in `create_fts_tables.sql` auf ausschließlich `unicode61 remove_diacritics 2` umstellen und gewinnt damit schnellere Indexierung auf Kosten der Suchqualität.

## Drei Suchanfragen

Am deutlichsten zeigt sich, was die Suchmaschine tut, wenn man sie einfach laufen lässt. Wir haben drei Anfragen gewählt, die die Ranking-Signale auf unterschiedliche Weise beanspruchen.

### newton — ein klarer Erfolg

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Isaac Newton | -20,69 | 1,37e-5 |
| 2 | Newton | -25,35 | 2,43e-8 |
| 3 | Knewton | -24,64 | 5,82e-8 |
| 4 | Enewton | -24,64 | 4,56e-8 |
| 5 | Newton-X | -23,96 | 2,87e-8 |

Isaac Newton landet auf Rang 1 mit dem besten BM25-Wert und einem PageRank, der etwa 200-mal höher liegt als der aller anderen Ergebnisse. Der Rest der Liste ist Trigramm-Rauschen — Artikel, deren Titel den Teilstring "newton" enthalten. Das Ranking bewältigt das hier korrekt, weil der Abstand zwischen Isaac Newton und allem anderen auf beiden Signalen gleichzeitig groß genug ist.

### relativity — ein gemischtes Ergebnis

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | General relativity | -26,32 | 9,92e-7 |
| 2 | Relativity Records | -26,32 | 8,41e-7 |
| 3 | Relativity Media | -26,32 | 7,93e-7 |
| 4 | Special relativity | -26,32 | 6,41e-7 |
| 5 | Relativity | -30,72 | 2,43e-8 |
| 6 | Theory of relativity | -23,17 | 9,43e-7 |

"Theory of relativity" hat den besten BM25-Wert in der Liste (-23,17 gegenüber -26,32 bei den anderen) und einen PageRank, der mit General relativity vergleichbar ist. Trotzdem landet er auf Rang 6. Der Grund: Die vier Spitzenergebnisse erzielen identische BM25-Werte, weil der Trigramm-Tokenizer "relativity" in jedem dieser Titel gleich gut als Teilstring trifft — PageRank allein trennt sie dann. Bei alpha gleich 0,8 dominiert BM25 bereits das Gesamtscore — doch wenn die BM25-Werte eng beieinanderliegen, reicht selbst ein deutlicher BM25-Vorsprung nicht immer aus, um einen PageRank-Nachteil auszugleichen. Ein Mensch würde "Theory of relativity" auf Platz 1 setzen; die Suchmaschine kann die Absicht hinter der Anfrage nicht erschließen.

### mercury — ein leises Versagen

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Mercury Records | -22,37 | 1,23e-5 |
| 2 | Mercury | -26,86 | 2,43e-8 |
| 3 | Mercury4 | -26,12 | 4,15e-8 |
| 4 | Mercury (planet) | -22,37 | 6,39e-6 |
| 5 | Mercury-P | -25,42 | 2,78e-8 |

Der Planet, das chemische Element, die römische Gottheit — keiner in den Top 5. Mercury Records belegt Rang 1, weil es bei BM25 gleichauf mit Mercury (planet) liegt, aber einen etwa doppelt so hohen PageRank aufweist. Ein Plattenlabel schlägt einen Planeten, weil es im Linkgraphen besser vernetzt ist — nicht weil es der wahrscheinlichere Referent für eine einsilbige Suchanfrage wäre. Die Begriffsklärungsseite auf Rang 2 mit schwachen Werten auf beiden Signalen ist dabei das ungünstigste denkbare Ergebnis: Sie ist nie die richtige Antwort und versperrt dem Planeten den Weg nach oben. Das ist dasselbe strukturelle Problem wie zuvor — Linkdichte als Ersatz für Relevanz — nur mit einem anderen Übeltäter als dem Ford/Mercury-Automodell-Cluster.

## Bewertung mit nDCG

Diese drei Beispiele geben Intuition — aber Intuition über einzelne Anfragen ist unzuverlässig. Was man braucht, ist ein Benchmark.

Wir haben die SemSearch_ES-Teilmenge von DBpedia-Entity v2 verwendet — einen keyword-orientierten Benchmark zur Entitätssuche mit menschlich annotierten Relevanzurteilen. Die Metrik ist nDCG@10: Normalised Discounted Cumulative Gain bei Rang 10. Sie belohnt das frühe Auffinden relevanter Dokumente in der Ergebnisliste und bestraft ihr Vergraben:

```
DCG@k = Σ rel_i / log2(i + 1)
```

Division durch das ideale DCG ergibt nDCG, einen Wert zwischen 0 und 1. Auf der vollständigen englischen Wikipedia erreicht die Suchmaschine einen mittleren nDCG@10 von **0,455**.

Zur Einordnung: Das DBpedia-Entity v2 Leaderboard (verfügbar unter [iai-group.github.io/DBpedia-Entity](https://iai-group.github.io/DBpedia-Entity/)) enthält eine Reihe von Retrieval-Modellen, die auf demselben Benchmark bewertet wurden. Reines BM25 erzielt 0,2497 auf SemSearch_ES. Die stärkeren Modelle — Sprachmodell-Varianten mit Entity Linking und feldgewichteter Bewertung — erreichen Werte zwischen 0,62 und 0,65. Unser Ergebnis liegt deutlich über der BM25-Baseline und unterhalb der ausgereiften Retrieval-Modelle — genau dort, wo man ein System erwartet, das ausschließlich Keyword-Matching und Linkstruktur kombiniert, ohne Trainingsdaten und ohne semantisches Verständnis.

Die Anfragen newton und mercury zeigen präzise, wo die verbleibende Lücke liegt: Disambiguierungsfehler und der grundlegende Unterschied zwischen struktureller Vernetzung und thematischer Relevanz.

## Was helfen würde

Beide Versagensmuster weisen in dieselbe Richtung. Mercury und relativity sind Anfragen, deren "richtige" Interpretation von einer Absicht abhängt, die Keyword-Matching nicht erschließen kann. Die strukturellen Lösungsansätze sind bekannt:

**Query Expansion und Entity Linking** würden bei mercury helfen, indem die prominenteste benannte Entität identifiziert und direkt aufgewertet wird — genau das implementieren die ELR-Varianten im Leaderboard, und ihre Verbesserungen gegenüber den Basismodellen sind konsistent. **Semantische Embeddings** würden helfen, indem Anfrageabsicht statt Oberflächenbegriffe kodiert werden — ein Dense-Retrieval-Modell würde Mercury (planet) unabhängig vom PageRank vor einem Plattenlabel platzieren. Beide Ansätze erhöhen Komplexität und Latenz; keiner ist ein direkter Ersatz für die bestehende Architektur.

Die Stärken des aktuellen Systems — Geschwindigkeit, Nachvollziehbarkeit, kein GPU-Bedarf — sind real. Für eindeutige Entitätsanfragen wie newton funktioniert es gut. Für einsilbige Substantive mit vielen gültigen Referenten nicht — und ein zweites Signal behebt nicht, was im Kern ein Disambiguierungsproblem ist.

## Fazit

Die Suchmaschine zu bauen war unkompliziert. Das Schwierigere war, ein Evaluierungs-Harness zu bauen, dem man vertrauen kann — und dann bereit zu sein, Anfragen zu stellen, die die Lücken sichtbar machen. nDCG@10 von 0,455 auf der vollständigen englischen Wikipedia hat uns eine Zahl gegeben; mercury und relativity haben uns ein Verständnis davon gegeben, was diese Zahl bedeutet.

Das Nützlichste, was ein Benchmark tun kann, ist präzise aufzuzeigen, was nicht funktioniert. Unserer tut es.

—-

*Der vollständige Code, einschließlich des Evaluierungs-Harness, ist Open Source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*
