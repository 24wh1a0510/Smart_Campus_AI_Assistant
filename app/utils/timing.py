from __future__ import annotations

import logging
import time
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("college_faq_chatbot")


@contextmanager
def timer():
    start = time.perf_counter()
    result = {"ms": 0.0}
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - start) * 1000
