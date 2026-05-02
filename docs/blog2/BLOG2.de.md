# Wikipedia durchsuchen: BM25, PageRank und die Grenzen von beidem

Eine Suchmaschine zu bauen ist einfach. Eine zu bauen, der man vertrauen kann, ist schwerer. Nach der Berechnung von PageRank über den gesamten Wikipedia-Linkgraphen lag die nächste Frage auf der Hand: Lassen sich diese Ränge nutzen, um Suchergebnisse zu verbessern? Und sobald wir eine Antwort hatten, brauchten wir eine Möglichkeit, sie zu messen.

Dieser Beitrag beschreibt, wie wir eine Keyword-Suchmaschine auf unserer Wikipedia-Pipeline aufgebaut haben — und was drei Suchanfragen über ihre Stärken und Grenzen verraten.

## Die Architektur: Zwei Streams, ein Ranking

Die Suchmaschine führt zwei parallele FTS-Anfragen gegen SQLite aus: eine über Seitentitel, eine über den Einleitungstext. Beide nutzen SQLite's FTS5 mit einem Trigramm-Tokenizer, der Teilstring-Suche ermöglicht — auf Kosten eines größeren Index. Die Ergebnisse werden zusammengeführt und nach einer gewichteten Kombination aus BM25 und PageRank neu geordnet.

BM25 misst, wie gut ein Dokument zur Anfrage passt. PageRank misst, wie wichtig das Dokument im Linkgraphen ist. Kein Signal allein reicht aus: BM25 ohne PageRank liefert obskure Seiten, die zufällig die Suchbegriffe enthalten; PageRank ohne BM25 schiebt bedeutende Artikel nach oben, unabhängig von ihrer Relevanz für die Anfrage. Die Kombination belohnt Seiten, die sowohl gut zur Anfrage passen als auch gut vernetzt sind.

Die Fusionsformel normalisiert beide Signale vor der Kombination:

```python
norm_bm25 = -bm25 / minimum_bm25
norm_rank = -rank / maximum_rank
score = alpha * norm_bm25 + (1 - alpha) * norm_rank
```

Die negativen Vorzeichen entstehen, weil FTS5 BM25 als negative Zahl zurückgibt — kleiner (negativer) bedeutet besser. Alpha steuert die Balance; wir haben uns für 0,5 entschieden und damit beiden Signalen gleiches Gewicht gegeben.

## Stoppwort-Filterung via IDF

Vor der eigentlichen Anfrage filtern wir hochfrequente Begriffe anhand von IDF-Werten aus den FTS-Vokabular-Tabellen heraus. Der Gedanke: Ein Begriff, der in fast jedem Dokument vorkommt, trägt kaum zur Unterscheidung bei — seine Aufnahme in die Anfrage erzeugt Rauschen ohne Gewinn. Der Schwellenwert liegt bei IDF ≥ 1,5. Wenn alle Begriffe darunter fallen, wird der Begriff mit dem höchsten IDF-Wert behalten — die Anfrage muss etwas enthalten.

Das ist ein günstiger, aber wirksamer Ersatz für eine handgepflegte Stoppwortliste. Sie passt sich dem Korpus an, statt ein festes Vokabular vorauszusetzen, und verursacht zur Anfragezeit keinen Mehraufwand, da FTS5 die Vokabularstatistiken bereits vorhält.

## Der Trigramm-Kompromiss

Wir haben uns für den Trigramm-Tokenizer gegenüber unicode61 entschieden, weil er die Suchqualität messbar verbessert. Trigramm-Indexierung ermöglicht Teilstring-Suche: Eine Anfrage nach „Einstein" findet „Albert Einstein" auch ohne Präfix-Anker. Der Kompromiss ist erheblich — der FTS-Index ist deutlich größer, und sein Aufbau gegen die vollständige englische Wikipedia dauert rund zwei Stunden.

Wer keine Suche benötigt oder einen kleineren Index bevorzugt, kann in `create_fts_tables.sql` auf `unicode61 remove_diacritics 2` umstellen und gewinnt damit schnellere Indexierung auf Kosten der Suchqualität.

## Drei Suchanfragen

Am deutlichsten zeigt sich, was die Suchmaschine tut, wenn man sie einfach laufen lässt. Wir haben drei Anfragen gewählt, die die Ranking-Signale auf unterschiedliche Weise beanspruchen.

### relativity — ein klarer Erfolg

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Theory of relativity | -15,77 | 9,43e-7 |
| 2 | Relativity Media | -16,03 | 7,93e-7 |
| 3 | Special relativity | -15,48 | 6,41e-7 |
| 4 | The Meaning of Relativity | -15,49 | 4,04e-7 |
| 5 | History of special relativity | -15,90 | 1,48e-7 |

Die Suchmaschine arbeitet hier wie vorgesehen. „Theory of relativity" landet auf Rang 1 mit starken Werten bei beiden Signalen. „Special relativity" und der Geschichtsartikel folgen in plausibler Reihenfolge. „Relativity Media" — ein Medienunternehmen, kein Physikkonzept — erscheint auf Rang 2, weil sein PageRank tatsächlich hoch ist und der Titel exakt passt. Ein Mensch würde ihn weiter hinten einordnen; die Suchmaschine kann die Absicht hinter der Anfrage nicht kennen.

### mercury — ein leises Versagen

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | Mercury Marquis | -12,63 | 1,58e-7 |
| 2 | Mercury-Atlas | -12,66 | 1,56e-7 |
| 3 | Mercury Monterey | -12,61 | 1,44e-7 |
| 4 | Mercury 7 | -12,71 | 1,42e-7 |
| 5 | List of Mercury-crossing minor planets | -12,59 | 1,16e-7 |

Der Planet Merkur, das chemische Element, die römische Gottheit — keiner von ihnen taucht auf. Die Top-10-Ergebnisse werden von Ford/Mercury-Automodellen und verwandten Artikeln dominiert. Das liegt daran, dass Wikipedia Hunderte von Stub-Artikeln über Mercury-Fahrzeuge enthält, die allesamt den Suchbegriff treffen und durch gegenseitige Verlinkung innerhalb des Clusters einen moderaten, aber konsistenten PageRank aufbauen. Kein einzelner Artikel dominiert — der Cluster tut es. Das ist ein strukturelles Artefakt, kein Relevanzsignal. Die Suchmaschine kann beides nicht unterscheiden.

### newton — ein deutliches Versagen

| Rang | Titel | BM25 | PageRank |
|------|-------|------|----------|
| 1 | National Register of Historic Places listings in Newton, Massachusetts | -12,80 | 1,11e-6 |
| 2 | West Newton, Massachusetts | -12,64 | 4,60e-7 |
| 3 | Newton Upper Falls | -12,58 | 1,07e-7 |
| 4 | Newton-by-the-Sea | -12,60 | 7,10e-8 |
| 5 | Religious views of Isaac Newton | -12,60 | 4,67e-8 |

Isaac Newton erscheint nicht. Das erste Ergebnis — ein Eintrag des National Register of Historic Places für eine Stadt in Massachusetts — landet ganz oben, weil Tausende von NRHP-Listenartikeln auf ihn verweisen und seinen PageRank weit über das hinaus aufblähen, was sein Inhalt für diese Anfrage rechtfertigen würde. Die BM25-Werte der Spitzenergebnisse sind nahezu identisch (alle um -12,6 bis -12,8), also entscheidet PageRank — und entscheidet falsch.

Das ist die deutlichste Illustration dessen, was PageRank tatsächlich misst: Linkstruktur, nicht Wichtigkeit im menschlichen Sinne. „National Register of Historic Places listings in Newton, Massachusetts" ist gut vernetzt innerhalb eines großen, dicht verlinkten Artikelclusters. Auch der Artikel über Isaac Newton ist gut vernetzt — er heißt aber *Isaac Newton*, nicht *Newton*, trifft die Trigramm-Anfrage daher schwächer, und PageRank kann nicht kompensieren, was BM25 verfehlt.

## Bewertung mit nDCG

Diese drei Beispiele geben Intuition — aber Intuition über einzelne Anfragen ist unzuverlässig. Was man braucht, ist ein Benchmark.

Wir haben die SemSearch_ES-Teilmenge von DBpedia-Entity v2 verwendet — einen keyword-orientierten Benchmark zur Entitätssuche mit menschlich annotierten Relevanzurteilen. Die Metrik ist nDCG@10: Normalised Discounted Cumulative Gain bei Rang 10. Sie belohnt das frühe Auffinden relevanter Dokumente in der Ergebnisliste und bestraft ihr Vergraben:

```
DCG@k = Σ rel_i / log2(i + 1)
```

Division durch das ideale DCG ergibt nDCG, einen Wert zwischen 0 und 1. Auf der vollständigen englischen Wikipedia erreicht die Suchmaschine einen mittleren nDCG@10 von **0,37**.

Diese Zahl ist ehrlich einzuordnen. Sie ist kein Misserfolg — 0,37 auf einem Benchmark, der für semantische Retrieval-Systeme entwickelt wurde, allein mit Keyword-Matching und Linkstruktur, ist ein respektables Ergebnis. Aber die Anfragen newton und mercury zeigen genau, wo die verbleibenden 0,63 bleiben: Disambiguierungsfehler, Cluster-Inflation und die grundlegende Lücke zwischen struktureller Wichtigkeit und thematischer Relevanz.

## Was helfen würde

Beide Versagensmuster weisen in dieselbe Richtung. Mercury und newton sind mehrdeutige Begriffe, deren „richtige" Interpretation von einer Anfrageabsicht abhängt, die Keyword-Matching nicht erschließen kann. Die strukturellen Lösungsansätze sind bekannt:

**Query Expansion und Entity Linking** würden bei mercury und newton helfen, indem die prominenteste benannte Entität für jeden Begriff identifiziert und direkt aufgewertet wird. **Semantische Embeddings** würden helfen, indem Anfrageabsicht statt Oberflächenbegriffe kodiert werden — ein Dense-Retrieval-Modell würde Isaac Newton unabhängig von BM25-Werten weit vor einer Stadt in Massachusetts platzieren. Beide Ansätze erhöhen Komplexität und Latenz; keiner ist ein direkter Ersatz für die bestehende Architektur.

Die Stärken des aktuellen Systems — Geschwindigkeit, Nachvollziehbarkeit, kein GPU-Bedarf — sind real. Für eindeutige Entitätsanfragen funktioniert es gut. Für einsilbige Substantive mit vielen gültigen Referenten nicht — und ein zweites Signal behebt nicht, was im Kern ein Disambiguierungsproblem ist.

## Fazit

Die Suchmaschine zu bauen war unkompliziert. Das Schwierigere war, ein Evaluierungs-Harness zu bauen, dem man vertrauen kann — und dann bereit zu sein, Anfragen zu stellen, die die Lücken sichtbar machen. nDCG@10 von 0,37 auf der vollständigen englischen Wikipedia hat uns eine Zahl gegeben; mercury und newton haben uns ein Verständnis davon gegeben, was diese Zahl bedeutet.

Das Nützlichste, was ein Benchmark tun kann, ist präzise aufzuzeigen, was nicht funktioniert. Unserer tut es.

---

*Der vollständige Code, einschließlich des Evaluierungs-Harness, ist Open Source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*