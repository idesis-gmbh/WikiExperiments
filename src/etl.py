import bz2
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED, as_completed
import cProfile
from itertools import islice
import pstats
import sqlite3
import time
import xml.etree.ElementTree as ET
import mwparserfromhell

INDEX_FILE_NAME = "data/enwiki-20260301-pages-articles-multistream-index.txt.bz2"
DATA_FILE_NAME = "data/enwiki-20260301-pages-articles-multistream.xml.bz2"
DB_FILE_NAME = "data/wiki.db"


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
            title = rest
        else:
            ns = 0
            title = text
    else:
        ns = 0
        title = text
    return ns, title


def transform_data(data_file_name, offset, full):
    data = extract_data(data_file_name, offset)
    xml = f"<root>{data.decode('utf-8')}</root>"
    root = ET.fromstring(xml)
    # dump_xml(root)
    for page in root.iter("page"):
        # dump_xml(page)
        title = page.find("title").text
        ns = page.find("ns").text
        page_id = page.find("id").text
        if full:
            redirect = page.find("redirect")
            if redirect is not None:
                redirection = True
                internal_links = {(0, redirect.attrib["title"])}
                external_links = {}
            else:
                redirection = False
                code = mwparserfromhell.parse(page.find("revision").find("text").text)
                internal_links = {
                    get_link_ns_title(str(link.title))
                    for link in code.filter_wikilinks()
                }
                external_links = {
                    str(link.url) for link in code.filter_external_links()
                }
        else:
            redirection = None
            internal_links = None
            external_links = None
        yield title, int(ns), int(page_id), redirection, internal_links, external_links


def transform_data_list(data_file_name, offset, full):
    return list(transform_data(data_file_name, offset, full))


def sqlite3_settings(connection):
    # connection.execute("PRAGMA journal_mode = persist")
    connection.execute("PRAGMA journal_mode = wal")
    connection.execute("PRAGMA cache_size = -4000000")


def init_data(connection, full):
    cursor = connection.cursor()
    cursor.execute("DELETE FROM redirects", ())
    cursor.execute("DELETE FROM external_links", ())
    cursor.execute("DELETE FROM external_pages", ())
    cursor.execute("DELETE FROM internal_links", ())
    if full:
        cursor.execute("DELETE FROM internal_pages", ())
    connection.commit()


def load_data(connection, generator, step):
    cursor = connection.cursor()
    for (
        title,
        ns,
        page_id,
        redirection,
        internal_links,
        external_links,
    ) in generator:
        # print(title, page_id, redirection)
        # for link in internal_links:
        #     print(" " * 2, link)
        # for link in external_links:
        #     print(" " * 2, link)
        if ns != 0:
            continue
        if step == 1:
            cursor.execute(
                "INSERT OR IGNORE INTO internal_pages (id, ns, title, text) VALUES (?, ?, ?, ?)",
                (page_id, ns, title, None),
            )
        elif step == 2:
            if not redirection:
                cursor.executemany(
                    "INSERT OR IGNORE INTO internal_links (source_id, target_id) SELECT ?, id FROM internal_pages WHERE ns = ? AND title = ?",
                    [(page_id, *link) for link in internal_links],
                )
                cursor.executemany(
                    "INSERT OR IGNORE INTO external_pages (url) VALUES (?)",
                    [(link,) for link in external_links],
                )
                cursor.executemany(
                    "INSERT OR IGNORE INTO external_links (source_id, target_id) SELECT ?, id FROM external_pages WHERE url = ?",
                    [(page_id, link) for link in external_links],
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO redirects (source_id, target_id) SELECT ?, id FROM internal_pages WHERE ns = ? AND title = ?",
                    (page_id, *next(iter(internal_links))),
                )
    connection.commit()


def run_serial_etl_data(step, slices=None):
    index_file_name = INDEX_FILE_NAME
    data_file_name = DATA_FILE_NAME
    with sqlite3.connect(DB_FILE_NAME) as connection:
        sqlite3_settings(connection)
        # init_data(connection)
        for offset, pages in (
            islice(transform_index(index_file_name), slices)
            if slices
            else transform_index(index_file_name)
        ):
            print(offset)
            load_data(
                connection, transform_data(data_file_name, offset, step == 2), step
            )


def run_parallel_etl_data(step, slices=None, max_workers=4):
    index_file_name = INDEX_FILE_NAME
    data_file_name = DATA_FILE_NAME
    with sqlite3.connect(DB_FILE_NAME) as connection:
        sqlite3_settings(connection)
        # init_data(connection)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = set()
            for offset, pages in (
                islice(transform_index(index_file_name), slices)
                if slices
                else transform_index(index_file_name)
            ):
                print(offset)
                futures.add(
                    executor.submit(
                        transform_data_list, data_file_name, offset, step == 2
                    )
                )
                if len(futures) > max_workers:
                    completed, futures = wait(futures, return_when=FIRST_COMPLETED)
                    for future in completed:
                        load_data(connection, future.result(), step)
            for future in as_completed(futures):
                load_data(connection, future.result(), step)


if __name__ == "__main__":
    start = time.time()
    # run_serial_etl_data(1, slices=2)
    # run_serial_etl_data(1)
    # run_serial_etl_data(2, slices=2)
    # run_serial_etl_data(2)
    # run_parallel_etl_data(1, max_workers=8)
    run_parallel_etl_data(2, max_workers=8)
    end = time.time()
    print(f"{end - start:.2f} seconds")
    """
    cProfile.run("run_serial_etl_data(2, slices=2)", "profile_results")
    p = pstats.Stats("profile_results")
    p.strip_dirs().sort_stats("cumulative").print_stats(20)
    start = time.time()
    run_serial_etl_data(1, slices=16)
    end = time.time()
    print(f"{end - start:.2f} seconds")
    for max_workers in [2, 4, 8]:
        start = time.time()
        run_parallel_etl_data(1, slices=16, max_workers=max_workers)
        end = time.time()
        print(f"{end - start:.2f} seconds")
    """
