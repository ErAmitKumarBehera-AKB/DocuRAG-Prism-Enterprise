import time
from contextlib import contextmanager


@contextmanager
def stage_timer():
    start = time.perf_counter()
    result = {"ms": 0.0}
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - start) * 1000.0
