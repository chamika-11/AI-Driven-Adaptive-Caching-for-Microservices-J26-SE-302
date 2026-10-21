"""A tiny thread-safe metric store and an HTTP endpoint in the Prometheus text format (no third-party package)."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


class MetricStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gauges: dict[tuple, float] = {}
        self._counters: dict[tuple, float] = {}
        self._help: dict[str, str] = {}

    @staticmethod
    def _key(name: str, labels: dict) -> tuple:
        return (name, tuple(sorted((k, str(v)) for k, v in labels.items())))

    def describe(self, name: str, text: str) -> None:
        self._help[name] = text

    def set(self, name: str, value: float, **labels) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = float(value)

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        k = self._key(name, labels)
        with self._lock:
            self._counters[k] = self._counters.get(k, 0.0) + float(value)

    def set_counter(self, name: str, value: float, **labels) -> None:
        """Counters whose total is maintained elsewhere (monotone within one replay run)."""
        with self._lock:
            self._counters[self._key(name, labels)] = float(value)

    def replace(self, name: str, items, **match) -> None:
        """Atomically replace every gauge ``name`` whose labels include ``match`` by ``items`` = [(labels, value)]."""
        want = {k: str(v) for k, v in match.items()}
        with self._lock:
            for k in [k for k in self._gauges if k[0] == name and all(dict(k[1]).get(a) == b for a, b in want.items())]:
                del self._gauges[k]
            for labels, value in items:
                self._gauges[self._key(name, {**match, **labels})] = float(value)

    def get(self, name: str, **labels) -> float | None:
        k = self._key(name, labels)
        with self._lock:
            return self._gauges.get(k, self._counters.get(k))

    def render(self) -> str:
        with self._lock:
            groups: dict[str, list] = {}
            for (n, lab), v in self._gauges.items():
                groups.setdefault(n, []).append(("gauge", lab, v))
            for (n, lab), v in self._counters.items():
                groups.setdefault(n, []).append(("counter", lab, v))
        out = []
        for n in sorted(groups):
            kind = groups[n][0][0]
            if n in self._help:
                out.append(f"# HELP {n} {self._help[n]}")
            out.append(f"# TYPE {n} {kind}")
            for _, lab, v in groups[n]:
                ls = ",".join(f'{k}="{_esc(val)}"' for k, val in lab)
                out.append(f"{n}{{{ls}}} {v:.10g}" if ls else f"{n} {v:.10g}")
        return "\n".join(out) + "\n"


def serve(store: MetricStore, port: int = 8000, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def do_GET(self):                                           # noqa: N802
            if self.path.split("?")[0] in ("/metrics", "/"):
                body = store.render().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):                                  # silence per-request logging
            pass

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
