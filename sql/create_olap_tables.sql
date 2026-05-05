DROP TABLE IF EXISTS external_domain_authority;
DROP TABLE IF EXISTS tld_authority;
DROP TABLE IF EXISTS internal_page_authority;

CREATE TABLE external_domain_authority AS
    SELECT
        ed.id as domain_id,
        ed.name,
        ed.tld,
        COUNT(DISTINCT el.source_id) AS citing_pages,
        AVG(ip.rank1) AS avg_citing_pagerank,
        SUM(ip.rank1) AS total_citing_pagerank
    FROM internal_pages ip
    JOIN external_links el ON el.source_id = ip.id
    JOIN external_pages ep ON el.target_id = ep.id
    JOIN external_domains ed ON ep.domain_id = ed.id
    WHERE ip.ns = 0
    GROUP BY ALL;

CREATE TABLE tld_authority AS
    SELECT
        tld,
        COUNT(*) AS domains,
        SUM(citing_pages) AS citing_pages,
        AVG(avg_citing_pagerank) AS avg_citing_pagerank,
        SUM(total_citing_pagerank) AS total_citing_pagerank
    FROM external_domain_authority
    GROUP BY ALL;

CREATE TABLE internal_page_authority AS
    SELECT
        el.source_id AS page_id,
        COUNT(DISTINCT da.domain_id) AS distinct_domains,
        SUM(da.total_citing_pagerank) AS total_citing_pagerank
    FROM external_links el
    JOIN external_pages ep ON el.target_id = ep.id
    JOIN external_domain_authority da ON da.domain_id = ep.domain_id
    GROUP BY ALL;
    
