UPDATE internal_pages
        SET in_degree = (
            SELECT COUNT(*)
            FROM internal_links
            WHERE internal_links.target_id = internal_pages.id
        ), out_degree = (
            SELECT COUNT(*)
            FROM internal_links
            WHERE internal_links.source_id = internal_pages.id
        ) 