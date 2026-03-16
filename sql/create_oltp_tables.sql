DROP TABLE IF EXISTS redirects;
DROP TABLE IF EXISTS external_links;
DROP TABLE IF EXISTS external_pages;
DROP TABLE IF EXISTS external_domains;
DROP TABLE IF EXISTS internal_links;
DROP TABLE IF EXISTS internal_pages;

CREATE TABLE internal_pages (
    id INTEGER,
    ns INTEGER,
    title TEXT,
    text TEXT,
    in_degree INTEGER,
    out_degree INTEGER,
    rank1 REAL,
    rank2 REAL,
    PRIMARY KEY(id),
    UNIQUE(ns, title)
);

CREATE TABLE internal_links (
    source_id INTEGER,
    target_id INTEGER,
    PRIMARY KEY(source_id, target_id),
    FOREIGN KEY(source_id) REFERENCES internal_pages(id),
    FOREIGN KEY(target_id) REFERENCES internal_pages(id)
);

CREATE TABLE external_domains (
    id INTEGER,
    name TEXT,
    tld TEXT,
    PRIMARY KEY(id),
    UNIQUE(name)
);

CREATE TABLE external_pages (
    id INTEGER,
    url TEXT,
    domain_id INTEGER,
    PRIMARY KEY(id),
    UNIQUE(url),
    FOREIGN KEY(domain_id) REFERENCES external_domains(id)
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