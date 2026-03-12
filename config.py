from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"

WIKI_DATE = "latest"
WIKI_NAME = "simplewiki"

INDEX_FILE_NAME = (
    f"{DATA_DIR}/{WIKI_NAME}-{WIKI_DATE}-pages-articles-multistream-index.txt.bz2"
)
DATA_FILE_NAME = (
    f"{DATA_DIR}/{WIKI_NAME}-{WIKI_DATE}-pages-articles-multistream.xml.bz2"
)
OLTP_DB_FILE_NAME = f"{DATA_DIR}/{WIKI_NAME}-oltp.db"
OLAP_DB_FILE_NAME = f"{DATA_DIR}/{WIKI_NAME}-olap.db"

MAX_WORKERS = 8
