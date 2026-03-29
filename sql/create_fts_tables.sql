DROP TABLE IF EXISTS internal_pages_fts;

CREATE VIRTUAL TABLE internal_pages_fts USING fts5(
    title,
    text,
    content='internal_pages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
    -- tokenize='porter unicode61 remove_diacritics 2'
    -- tokenize='trigram'
);

INSERT INTO internal_pages_fts(rowid, title, text)
SELECT id, title, text FROM internal_pages;

CREATE TRIGGER IF NOT EXISTS internal_pages_ai
AFTER INSERT ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(rowid, title, text)
    VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS internal_pages_ad
AFTER DELETE ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(internal_pages_fts, rowid)
    VALUES ('delete', old.id);
END;

CREATE TRIGGER IF NOT EXISTS internal_pages_au
AFTER UPDATE OF id, title, text ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(internal_pages_fts, rowid)
    VALUES ('delete', old.id);
    INSERT INTO internal_pages_fts(rowid, title, text)
    VALUES (new.id, new.title, new.text);
END;

