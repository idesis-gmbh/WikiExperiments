insert into internal_pages(id) values (1);
insert into internal_pages(id) values (2);
insert into internal_pages(id) values (3);
insert into internal_pages(id) values (4);

insert into internal_links(source_id, target_id) values(1, 2);
insert into internal_links(source_id, target_id) values(1, 3);
insert into internal_links(source_id, target_id) values(2, 1);
insert into internal_links(source_id, target_id) values(3, 1);