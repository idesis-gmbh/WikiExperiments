# Was weiß Wikipedia wirklich? PageRank, SQL und ein überraschender Käfer

Wikipedia ist die größte von Menschen kuratierte Wissenssammlung der Welt. Millionen von Artikeln, Hunderte von Millionen interner Verlinkungen – und mittendrin eine Frage, die uns nicht losließ: Welche Artikel bilden eigentlich das Rückgrat dieses Wissensnetzes?

Um das herauszufinden, haben wir PageRank auf die englische Wikipedia angewendet – denselben Algorithmus, mit dem Google einst das Web sortiert hat. Das Ergebnis war aufschlussreich. Und an einer Stelle ziemlich unerwartet.

## PageRank: Wichtigkeit durch Verlinkung

PageRank wurde von Larry Page und Sergey Brin entwickelt, um Webseiten nach ihrer Bedeutung zu ordnen. Die Grundidee ist elegant: Eine Seite ist wichtig, wenn viele wichtige Seiten auf sie verlinken. Bedeutung pflanzt sich durch das Netz fort – iterativ, bis sich die Werte stabilisieren.

Wikipedia eignet sich hervorragend für diese Analyse. Die internen Links sind von Redakteuren gesetzt, inhaltlich bedeutsam und frei von kommerziellen Verzerrungen. Mit Millionen von Artikeln ist der Datensatz zudem groß genug, um rechnerische Entscheidungen wirklich spürbar zu machen.

## Die Pipeline: ETL in zwei Pässen

Wikipedia stellt seine Inhalte als komprimierte XML-Dumps zur Verfügung. Wir haben eine Pipeline gebaut, die diesen Dump in zwei parallelen Pässen mit `ProcessPoolExecutor` verarbeitet: zuerst werden alle Seiten geladen, dann interne Links, externe Links und Weiterleitungen. Das Ergebnis landet in einer SQLite-Datenbank – ohne den komprimierten Dump jemals vollständig zu entpacken. Für die englische Wikipedia wäre das unkomprimiert über 200 GB; die Pipeline streamt den Dump direkt.

## PageRank in reinem SQL

Die eigentliche Berechnung läuft vollständig in SQL – kein Python-Loop, kein externer Graph-Prozessor. Pro Iteration werden vier SQL-Statements ausgeführt: Rank-Reset, Weitergabe über verlinkte Seiten, Behandlung von nicht verlinkten Seiten und schließlich die Dämpfungsfaktor-Korrektur.

Ein Detail, das uns besonders gut gefällt: Statt in jeder Iteration eine neue temporäre Tabelle anzulegen, nutzen wir einen Ping-Pong-Puffer zwischen zwei Spalten (`rank1` und `rank2`). Das sichert konsistente Quellwerte innerhalb einer Iteration und vermeidet den Overhead für Anlage und Indexierung temporärer Tabellen.

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

Nach 21 Iterationen konvergiert der Algorithmus – der maximale Rankingunterschied zwischen zwei Durchläufen fällt unter 1e-6.

## SQLite vs. DuckDB: 50-facher Geschwindigkeitsunterschied

PageRank ist ein analytisch intensiver Workload: viele Aggregationen über große Mengen, viele Wiederholungen. Genau das macht ihn zu einem aufschlussreichen Benchmark für die Wahl der Datenbank-Engine.

Wir haben denselben Algorithmus gegen SQLite und DuckDB laufen lassen:

| Engine | Zeit (21 Iterationen) |
|--------|----------------------|
| SQLite | ~510 Sekunden |
| DuckDB | ~10 Sekunden |

DuckDB ist **50-mal schneller** – bei numerisch identischen Ergebnissen. Die Datenbank ist dazu noch 20-mal kleiner, dank spaltenorientierter Speicherung und Kompression. Für die vollständige englische Wikipedia bedeutet das den Unterschied zwischen einem Lauf, der Stunden dauert, und einem, der Minuten braucht.

## Die Ergebnisse: Was Wikipedia für wichtig hält

Die Top-Artikel nach PageRank lesen sich wie ein Schnitt durch das kollektive Weltwissen:

| Rang | Artikel |
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

Großmächte, globale Medien, historische Zäsuren – das erscheint plausibel. Dann Platz 13:

**Cerambycidae.**

Eine Käferfamilie. Zwischen Weltkrieg und *The Guardian*. Das überraschte uns zunächst – und hat eine schöne Erklärung: Wikipedia enthält hunderttausende automatisch generierter Stub-Artikel zu Insektenarten, von denen viele auf die übergeordnete Familie zurückverlinken. PageRank misst Verlinkungsstruktur, nicht Relevanz im menschlichen Sinne – und genau das macht solche Ausreißer zu wertvollen Datenpunkten.

## Fazit

Dieses Projekt zeigt, was möglich ist, wenn man Wikipedia als Rohmaterial für eigene Analysen begreift: eine großvolumige ETL-Pipeline, SQL als vollwertige Berechnungssprache für iterative Graphalgorithmen, und ein direkter Leistungsvergleich zwischen zwei Datenbank-Engines bei realem Workload.

Die Wahl der richtigen Technologie ist dabei keine akademische Frage – sie ist der Unterschied zwischen einem Experiment, das läuft, und einem, das wartet.

---

*Neugierig geworden? Das Projekt ist Open Source: [github.com/idesis-gmbh/wikiexperiments](https://github.com/idesis-gmbh/wikiexperiments)*