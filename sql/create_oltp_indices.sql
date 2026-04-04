CREATE INDEX internal_texts_hash ON internal_texts(hash);
CREATE INDEX internal_pages_text_id ON internal_pages(text_id);
CREATE INDEX internal_links_target_id ON internal_links(target_id);
CREATE INDEX external_parges_domain_id ON external_pages(domain_id);
CREATE INDEX external_links_target_id ON external_links(target_id);
CREATE INDEX redirects_links_target_id ON redirects(target_id);
