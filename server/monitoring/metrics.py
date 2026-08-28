from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
from flask import request, Response

# ---- 指标定义 ----
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "status"]
)
HTTP_REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds", "HTTP request latency",
    ["method", "endpoint"], buckets=[0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
)

CACHE_HIT = Counter("cache_hit_total", "Semantic cache hits", ["layer"])
CACHE_MISS = Counter("cache_miss_total", "Semantic cache misses", ["layer"])

RETRIEVE_LATENCY = Histogram(
    "retrieve_latency_seconds", "Retrieval latency breakdown",
    ["stage"], buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1, 2]
)  # stage: bm25, vector, rrf, rerank, total

GENERATE_LATENCY = Histogram(
    "generate_latency_seconds", "LLM generation latency",
    ["model"], buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
)

ACTIVE_REQUESTS = Gauge("active_requests", "Currently processing requests")

# ---- 中间件 ----
def monitor_middleware(app):
    @app.before_request
    def _start():
        request._start_ts = time.time()
        ACTIVE_REQUESTS.inc()

    @app.after_request
    def _record(resp):
        latency = time.time() - request._start_ts
        ACTIVE_REQUESTS.dec()
        HTTP_REQUESTS_TOTAL.labels(
            request.method, request.path, resp.status_code
        ).inc()
        HTTP_REQUEST_LATENCY.labels(request.method, request.path).observe(latency)
        return resp

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)