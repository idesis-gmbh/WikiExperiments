DROP VIEW IF EXISTS internal_page_profile;
    
CREATE VIEW internal_page_profile AS
    SELECT
        ip.id AS page_id,
        ip.ns,
        ip.title,
        ep.url,
        ed.name AS domain,
        ed.tld,
        COUNT(*) OVER (PARTITION BY ip.id, ed.id) AS domain_citation_count
    FROM internal_pages ip
    JOIN external_links el ON el.source_id = ip.id
    JOIN external_pages ep ON el.target_id = ep.id
    JOIN external_domains ed ON ep.domain_id = ed.id;

