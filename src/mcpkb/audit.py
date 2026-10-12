import json
import logging
import sys
import time
from collections import defaultdict
from contextlib import contextmanager

# stdout belongs to the stdio transport, so audit lines go to stderr
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
log = logging.getLogger("mcpkb.audit")
log.addHandler(_handler)
log.setLevel(logging.INFO)
log.propagate = False


class Audit:
    def __init__(self):
        self.calls = defaultdict(int)
        self.errors = defaultdict(int)
        self.total_ms = defaultdict(float)

    @contextmanager
    def track(self, tool: str, **fields):
        start = time.monotonic()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            ms = (time.monotonic() - start) * 1000
            self.calls[tool] += 1
            self.total_ms[tool] += ms
            if not ok:
                self.errors[tool] += 1
            log.info(json.dumps({"tool": tool, "ok": ok, "ms": round(ms, 2), **fields}, default=str))

    def snapshot(self) -> dict:
        return {
            tool: {"calls": n, "errors": self.errors[tool], "avg_ms": round(self.total_ms[tool] / n, 2)}
            for tool, n in sorted(self.calls.items())
        }
