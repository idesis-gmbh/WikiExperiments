import bz2
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED, as_completed
import hashlib
from itertools import islice
from pathlib import Path
from time import time
import xml.etree.ElementTree as ET
import mwparserfromhell
import tldextract

from config import INDEX_FILE_NAME, DATA_FILE_NAME, OLTP_DB_FILE_NAME, MAX_WORKERS
from db import sqlite_connect


def extract_index(index_file_name):
    with bz2.open(index_file_name, "rt", encoding="utf-8") as index_file:
        for line in index_file:
            offset, page_id, title = line.rstrip("\n").split(":", 2)
            yield int(offset), int(page_id), title


def transform_index(index_file_name):
    data_file_offset = None
    for offset, page_id, title in extract_index(index_file_name):
        if not data_file_offset or data_file_offset[0] < offset:
            if data_file_offset:
                yield data_file_offset
            data_file_offset = (offset, [(page_id, title)])
        else:
            assert data_file_offset[0] == offset
            data_file_offset[1].append((page_id, title))
    if data_file_offset:
        yield data_file_offset


def extract_data(data_file_name, offset):
    with open(data_file_name, "rb") as data_file:
        data_file.seek(offset)
        decompressor = bz2.BZ2Decompressor()
        result = bytearray()
        while True:
            data = data_file.read(65536)
            if not data:
                break
            chunk = decompressor.decompress(data)
            result.extend(chunk)
            if decompressor.eof:  # or decompressor.unused_data:
                break
        return bytes(result)


def shorten_text(text):
    text = text.split("\n", 1)[0]
    if text:
        return text if len(text) < 80 else f"{text[:80]}..."
    return text


def dump_xml(parent, indent=0):
    for child in parent:
        print(" " * indent, child.tag, child.attrib)
        text = child.text
        if text:
            print(" " * indent, shorten_text(text))
        dump_xml(child, indent + 2)


def clean_wikitext(code):
    for link in code.filter_wikilinks():
        if link.title.startswith(("File:", "Image:", "file:", "image:")):
            try:
                code.remove(link)
            except ValueError:
                pass
    return code.strip_code().strip()


# fmt: off
NS_PREFIXES = {
    "": 0, "Talk": 1,
    "User": 2, "User talk": 3,
    "Wikipedia": 4, "Wikipedia talk": 5,
    "File": 6, "File talk": 7,
    "MediaWiki": 8, "MediaWiki talk": 9,
    "Template": 10, "Template talk": 11,
    "Help": 12, "Help talk": 13,
    "Category": 14, "Category talk": 15,
    "Portal": 100, "Portal talk": 101,
    "Draft": 118, "Draft talk": 119,
    "MOS": 126, "MOS talk": 127,
    "TimedText": 710, "TimedText talk": 711,
    "Module": 828, "Module talk": 829,
    "Event": 1728, "Event talk": 1729, 
}
# fmt: on


def get_link_ns_title(text):
    if ":" in text:
        prefix, rest = text.split(":", 1)
        if prefix in NS_PREFIXES:
            ns = NS_PREFIXES[prefix]
            title = f"{prefix}:{rest}" if prefix else rest
        else:
            ns = 0
            title = text
    else:
        ns = 0
        title = text
    return ns, title


def get_template_ns_titles(ns, title, code):
    for template in code.filter_templates():
        name = (
            str(template.name)
            .lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("+", "")
        )
        if name in [
            "commonscategory",
            "commonscategoryinline",
            "commonscategorymulti",
            "commonscat",
            "commonscatinline",
            "commonscatmulti",
            "commonscats",
            "commonsandcategory",
            "commonsandcategoryinline",
        ]:
            categories = template.params[0] if template.params else []
            if ns != 14 and not categories:
                categories = [title]
            yield {(14, f"Category:{category}") for category in categories}
        elif name.startswith("commons") and name not in [
            "commons",
            "commonscompact",
            "commonsinline",
        ]:
            # print(title, template.name, template.params)
            pass


def transform_data(data_file_name, offset, step):
    data = extract_data(data_file_name, offset)
    xml = f"<root>{data.decode('utf-8')}</root>"
    root = ET.fromstring(xml)
    # dump_xml(root)
    for page in root.iter("page"):
        # dump_xml(page)
        title = page.find("title").text
        ns = int(page.find("ns").text)
        page_id = int(page.find("id").text)
        redirect = page.find("redirect")
        redirection = redirect is not None
        if step == 1 and ns == 0 and not redirection:
            text = page.find("revision").find("text").text
            code = mwparserfromhell.parse(text)
            lead = clean_wikitext(code.get_sections(include_lead=True)[0])
            # assert lead
        else:
            lead = None
        if step == 2:
            if redirection:
                internal_links = {get_link_ns_title(redirect.attrib["title"])}
                external_links = set()
            else:
                text = page.find("revision").find("text").text
                code = mwparserfromhell.parse(text)
                internal_links = {
                    get_link_ns_title(str(link.title))
                    for link in code.filter_wikilinks()
                }.union(*get_template_ns_titles(ns, title, code))
                external_links = {
                    str(link.url) for link in code.filter_external_links()
                }
        else:
            internal_links = None
            external_links = None
        yield (
            title,
            ns,
            page_id,
            redirection,
            lead,
            internal_links,
            external_links,
        )


def transform_data_list(data_file_name, offset, step):
    return list(transform_data(data_file_name, offset, step))


def init_data(connection, full):
    cursor = connection.cursor()
    cursor.execute("DELETE FROM redirects")
    cursor.execute("DELETE FROM external_links")
    cursor.execute("DELETE FROM external_pages")
    cursor.execute("DELETE FROM internal_links")
    if full:
        cursor.execute("DELETE FROM internal_pages")
    connection.commit()


def load_data(connection, generator, step):
    cursor = connection.cursor()
    for (
        title,
        ns,
        page_id,
        redirection,
        lead,
        internal_links,
        external_links,
    ) in generator:
        # print(title, page_id, redirection)
        # for link in internal_links:
        #     print(" " * 2, link)
        # for link in external_links:
        #     print(" " * 2, link)
        if ns not in [0, 14]:
            continue
        if step == 1:
            lead_id = None
            if lead:
                hash = hashlib.md5(lead.encode("utf-8")).hexdigest()
                result = cursor.execute(
                    """
                    SELECT id, text
                    FROM internal_texts 
                    WHERE hash = ?
                    """,
                    (hash,),
                )
                for text_id, text in enumerate(result.fetchall()):
                    if text == lead:
                        lead_id = text_id
                        break
                if not lead_id:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO internal_texts (hash, text) 
                        VALUES (?, ?)
                        """,
                        (hash, lead),
                    )
                    lead_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT OR IGNORE INTO internal_pages (id, ns, title, text_id) 
                VALUES (?, ?, ?, ?)
                """,
                (page_id, ns, title, lead_id),
            )
        elif step == 2:
            if not redirection:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO internal_links (source_id, target_id) 
                    SELECT ?, id FROM internal_pages WHERE ns = ? AND title = ?
                    """,
                    [(page_id, *link) for link in internal_links],
                )
                external_domain_pages = {}
                for link in external_links:
                    extracted = tldextract.extract(link)
                    external_domain_pages[link] = (
                        f"{extracted.domain}.{extracted.suffix}",
                        extracted.suffix,
                    )
                external_domains = set(external_domain_pages.values())
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO external_domains (name, tld) 
                    VALUES (?, ?)
                    """,
                    [(domain, suffix) for domain, suffix in external_domains],
                )
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO external_pages (url, domain_id) 
                    SELECT ?, id FROM external_domains WHERE name = ?
                    """,
                    [
                        (link, domain)
                        for link, (domain, suffix) in external_domain_pages.items()
                    ],
                )
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO external_links (source_id, target_id) 
                    SELECT ?, id FROM external_pages WHERE url = ?
                    """,
                    [(page_id, link) for link in external_links],
                )
            else:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO redirects (source_id, target_id) 
                    SELECT ?, id FROM internal_pages WHERE ns = ? AND title = ?
                    """,
                    (page_id, *next(iter(internal_links))),
                )
    connection.commit()


def post_process_redirects(connection):
    cursor = connection.cursor()
    cursor.execute(
        """        
        UPDATE internal_pages AS sp
        SET text_id = tt.id
        FROM redirects r 
        INNER JOIN internal_pages tp ON tp.id = r.target_id
        INNER JOIN internal_texts tt on tt.id = tp.text_id
        WHERE sp.id = r.source_id 
        """,
    )
    connection.commit()


def run_serial_etl(step, slices=None):
    index_file_name = INDEX_FILE_NAME
    data_file_name = DATA_FILE_NAME
    with sqlite_connect() as connection:
        # NOTE: when developing you can remove old database contents here
        # init_data(connection)
        for index, (offset, pages) in enumerate(
            islice(transform_index(index_file_name), slices)
            if slices
            else transform_index(index_file_name)
        ):
            # print("Processing strean at offset", offset)
            load_data(
                connection, transform_data(data_file_name, offset, step == 2), step
            )
            if index % 100 == 0:
                print(".", end="", flush=True)
        print(flush=True)


def run_parallel_etl(step, slices=None, max_workers=MAX_WORKERS):
    index_file_name = INDEX_FILE_NAME
    data_file_name = DATA_FILE_NAME
    with sqlite_connect() as connection:
        # NOTE: when developing you can remove old database contents here
        # init_data(connection)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = set()
            for index, (offset, pages) in enumerate(
                islice(transform_index(index_file_name), slices)
                if slices
                else transform_index(index_file_name)
            ):
                # print("Processing strean at offset", offset)
                futures.add(
                    executor.submit(transform_data_list, data_file_name, offset, step)
                )
                if len(futures) > max_workers:
                    completed, futures = wait(futures, return_when=FIRST_COMPLETED)
                    for future in completed:
                        load_data(connection, future.result(), step)
                        if index % 100 == 0:
                            print(".", end="", flush=True)
            for future in as_completed(futures):
                load_data(connection, future.result(), step)
                if index % 100 == 0:
                    print(".", end="", flush=True)
        print(flush=True)


def post_process():
    with sqlite_connect() as connection:
        post_process_redirects(connection)


def init_schema():
    if Path(OLTP_DB_FILE_NAME).exists():
        print(f"Database {OLTP_DB_FILE_NAME} already exists, skipping schema init.")
        return
    with sqlite_connect() as connection:
        for file_name in ["sql/create_oltp_tables.sql"]:
            with open(file_name) as file:
                connection.executescript(file.read())


def update_schema():
    with sqlite_connect() as connection:
        for file_name in ["sql/create_oltp_indices.sql", "sql/create_fts_tables.sql"]:
            with open(file_name) as file:
                connection.executescript(file.read())


def run(max_workers=MAX_WORKERS):
    start = time()
    init_schema()
    end = time()
    print(f"Initialized schema: {end - start:.2f} seconds")
    start = time()
    run_parallel_etl(1, max_workers=max_workers)
    end = time()
    print(f"ETL step 1: {end - start:.2f} seconds")
    start = time()
    run_parallel_etl(2, max_workers=max_workers)
    end = time()
    print(f"ETL step 2: {end - start:.2f} seconds")
    # start = time()
    # post_process()
    # end = time()
    # print(f"Postprocess: {end - start:.2f} seconds")
    start = time()
    update_schema()
    end = time()
    print(f"Updated schema: {end - start:.2f} seconds")


if __name__ == "__main__":
    run()
