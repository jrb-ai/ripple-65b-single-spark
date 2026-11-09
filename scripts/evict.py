#!/usr/bin/env python3
"""Drop the page-cache pages of every file under the given directories (posix_fadvise DONTNEED; no root needed).

usage: evict.py DIR [DIR ...] [--loop SECONDS]   (--loop repeats until killed, for a download in progress)
The GB10 driver needs free pages, not reclaimable cache, so checkpoints read or written outside the engine are evicted.
"""
import os
import sys
import time


def evict(roots: list) -> int:
    """Evict each regular file's cached pages; return the number of files touched."""
    n = 0
    for root in roots:
        for d, _, fs in os.walk(root, followlinks=True):
            for f in fs:
                p = os.path.join(d, f)
                try:
                    fd = os.open(p, os.O_RDONLY)
                except OSError:
                    continue
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                    n += 1
                finally:
                    os.close(fd)
    return n


if __name__ == "__main__":
    args = sys.argv[1:]
    loop = None
    if "--loop" in args:
        i = args.index("--loop")
        loop = float(args[i + 1])
        del args[i:i + 2]
    while True:
        n = evict(args)
        if loop is None:
            print(f"evicted {n} files")
            break
        time.sleep(loop)
