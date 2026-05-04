from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"

WIKI_DATE = "latest"
WIKI_NAME = "simplewiki"
# WIKI_DATE = "20260301"
# WIKI_NAME = "enwiki"

INDEX_FILE_NAME = (
    f"{DATA_DIR}/{WIKI_NAME}-{WIKI_DATE}-pages-articles-multistream-index.txt.bz2"
)
DATA_FILE_NAME = (
    f"{DATA_DIR}/{WIKI_NAME}-{WIKI_DATE}-pages-articles-multistream.xml.bz2"
)
OLTP_DB_FILE_NAME = f"{DATA_DIR}/{WIKI_NAME}-oltp.db"
OLAP_DB_FILE_NAME = f"{DATA_DIR}/{WIKI_NAME}-olap.db"

MAX_WORKERS = 8

DAMPING_FACTOR = 0.85
MAX_ITERATIONS = 50
TOLERANCE = 1e-6

K1 = 100
K2 = 10
TITLE_WEIGHT_UNICODE = 2
TITLE_WEIGHT_TRIGRAM = 2
TEXT_WEIGHT_UNICODE = 1
TEXT_WEIGHT_TRIGRAM = 1
ALPHA = 0.8
