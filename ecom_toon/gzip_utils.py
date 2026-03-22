import gzip
from ecom_toon import toon

def write_gzip_toon(obj, filename):
    """Write TOON output to a gzip-compressed file."""
    toon_str = toon.json_to_toon(obj)
    with gzip.open(filename, 'wt', encoding='utf-8') as f:
        f.write(toon_str)


def read_gzip_toon(filename):
    """Read and return TOON string from a gzip-compressed file."""
    with gzip.open(filename, 'rt', encoding='utf-8') as f:
        return f.read()
