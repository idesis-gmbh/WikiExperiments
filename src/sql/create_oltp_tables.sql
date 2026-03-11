DROP TABLE IF EXISTS redirects;
DROP TABLE IF EXISTS external_links;
DROP TABLE IF EXISTS external_pages;
DROP TABLE IF EXISTS internal_links;
DROP TABLE IF EXISTS internal_pages;

CREATE TABLE internal_pages (
    id INTEGER,
    ns INTEGER,
    title TEXT,
    text TEXT,
    out_degree INTEGER,
    rank1 REAL,
    rank2 REAL,
    PRIMARY KEY(id),
    UNIQUE(ns, title)
);

CREATE TABLE pagerank (
    id INTEGER,
    rank REAL,
    PRIMARY KEY(id)
);

CREATE TABLE internal_links (
    source_id INTEGER,
    target_id INTEGER,
    PRIMARY KEY(source_id, target_id),
    FOREIGN KEY(source_id) REFERENCES internal_pages(id),
    FOREIGN KEY(target_id) REFERENCES internal_pages(id)
);

CREATE TABLE external_pages (
    id INTEGER,
    url TEXT,
    PRIMARY KEY(id),
    UNIQUE(url)
);

CREATE TABLE external_links (
    source_id INTEGER,
    target_id INTEGER,
    PRIMARY KEY(source_id, target_id),
    FOREIGN KEY(source_id) REFERENCES internal_pages(id),
    FOREIGN KEY(target_id) REFERENCES external_pages(id)
);

CREATE TABLE redirects (
    source_id INTEGER,
    target_id INTEGER,
    PRIMARY KEY(source_id),
    FOREIGN KEY(source_id) REFERENCES internal_pages(id),
    FOREIGN KEY(target_id) REFERENCES internal_pages(id)
);