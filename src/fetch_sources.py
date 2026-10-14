"""Step 1: download (or verify cached copies of) the remote source files.

The files are pinned to specific GitHub commits and checked against SHA-256
hashes, so a re-run produces byte-identical inputs. If the network is not
available, the cached copies in data/raw/ are verified and used.
"""
import hashlib
import sys
import urllib.request

from config import RAW, SOURCES


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(force=False):
    RAW.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        path = src["file"]
        if path.exists() and not force and sha256(path) == src["sha256"]:
            print(f"[fetch] {name}: cached copy verified ({path.name})")
            continue
        try:
            print(f"[fetch] {name}: downloading {src['url']}")
            with urllib.request.urlopen(src["url"], timeout=60) as r:
                data = r.read()
            path.write_bytes(data)
        except Exception as e:  # offline, proxy, etc.
            if path.exists():
                print(f"[fetch] {name}: download failed ({e}); using cached copy")
            else:
                sys.exit(f"[fetch] {name}: download failed and no cached copy: {e}")
        digest = sha256(path)
        if digest != src["sha256"]:
            sys.exit(f"[fetch] {name}: SHA-256 mismatch ({digest}); source file changed")
        print(f"[fetch] {name}: OK")


if __name__ == "__main__":
    fetch(force="--force" in sys.argv)
