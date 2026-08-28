# -*- coding: utf-8 -*-
"""
检索/生成链路监控埋点
在 retrievers.py 和 generator.py 的关键阶段上下文管理器式埋点
"""
from contextlib import contextmanager
import time
from monitoring.metrics import RETRIEVE_LATENCY, GENERATE_LATENCY, CACHE_HIT, CACHE_MISS

# ========== 检索阶段 ==========
@contextmanager
def timed_retrieve(stage: str):
    """检索各阶段计时"""
    t0 = time.time()
    try:
        yield
    finally:
        RETRIEVE_LATENCY.labels(stage=stage).observe(time.time() - t0)

@contextmanager
def timed_generate(model: str):
    """生成阶段计时"""
    t0 = time.time()
    try:
        yield
    finally:
        GENERATE_LATENCY.labels(model=model).observe(time.time() - t0)


def record_cache_hit(layer: str):
    """语义缓存命中"""
    CACHE_HIT.labels(layer=layer).inc()


def record_cache_miss(layer: str):
    """语义缓存未命中"""
    CACHE_MISS.labels(layer=layer).inc()
