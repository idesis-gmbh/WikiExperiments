DROP TABLE IF EXISTS internal_texts_fts;
DROP TABLE IF EXISTS internal_pages_fts;

CREATE VIRTUAL TABLE internal_texts_fts USING fts5(
    text,
    content='internal_texts',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
    -- tokenize='porter unicode61 remove_diacritics 2'
    -- tokenize='trigram'
);

INSERT INTO internal_texts_fts(rowid, text)
SELECT id, text FROM internal_texts;

CREATE TRIGGER IF NOT EXISTS internal_texts_ai
AFTER INSERT ON internal_texts
BEGIN
    INSERT INTO internal_texts_fts(rowid, text)
    VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS internal_texts_ad
AFTER DELETE ON internal_texts
BEGIN
    INSERT INTO internal_texts_fts(internal_texts_fts, rowid)
    VALUES ('delete', old.id);
END;

CREATE TRIGGER IF NOT EXISTS internal_texts_au
AFTER UPDATE OF id, text ON internal_texts
BEGIN
    INSERT INTO internal_texts_fts(internal_texts_fts, rowid)
    VALUES ('delete', old.id);
    INSERT INTO internal_texts_fts(rowid, text)
    VALUES (new.id, new.text);
END;

CREATE VIRTUAL TABLE internal_pages_fts USING fts5(
    title,
    content='internal_pages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
    -- tokenize='porter unicode61 remove_diacritics 2'
    -- tokenize='trigram'
);

INSERT INTO internal_pages_fts(rowid, title)
SELECT id, title FROM internal_pages;

CREATE TRIGGER IF NOT EXISTS internal_pages_ai
AFTER INSERT ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(rowid, title)
    VALUES (new.id, new.title);
END;

CREATE TRIGGER IF NOT EXISTS internal_pages_ad
AFTER DELETE ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(internal_pages_fts, rowid)
    VALUES ('delete', old.id);
END;

CREATE TRIGGER IF NOT EXISTS internal_pages_au
AFTER UPDATE OF id, title ON internal_pages
BEGIN
    INSERT INTO internal_pages_fts(internal_pages_fts, rowid)
    VALUES ('delete', old.id);
    INSERT INTO internal_pages_fts(rowid, title)
    VALUES (new.id, new.title, new.text);
END;

