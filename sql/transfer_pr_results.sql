COPY (SELECT id, rank1, rank2 FROM internal_pages) TO 'c:\users\jhrwa\documents\github\wikiexperiments\data\ranks.csv' (FORMAT CSV);

.import --csv 'c:\users\jhrwa\documents\github\wikiexperiments\data\ranks.csv' ranks_temporary
UPDATE internal_pages 
SET rank1 = temporary.rank1, rank2 = temporary.rank2
FROM ranks_temporary temporary 
WHERE internal_pages.id = temporary.id;