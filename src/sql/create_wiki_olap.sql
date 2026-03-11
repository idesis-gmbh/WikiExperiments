DETACH sqlite_db;
ATTACH 'c:\users\jhrwa\documents\github\wikiexperiments\data\wiki-oltp.db' AS sqlite_db (TYPE SQLITE);

CREATE TABLE internal_pages AS SELECT * FROM sqlite_db.internal_pages;
CREATE TABLE internal_links AS SELECT * FROM sqlite_db.internal_links


