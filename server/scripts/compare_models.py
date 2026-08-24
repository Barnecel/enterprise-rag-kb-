# -*- coding: utf-8 -*-
"""
模型 A/B 对比测试（RAG地狱五题）—— 直填URL版
用方法：
  1. 改下面 MODEL_A / MODEL_B 三个字段（api_base 含 /v1；本地服务 key 可随便填）
  2. ../.venv/bin/python scripts/compare_models.py        # 全量5题
     ../.venv/bin/python scripts/compare_models.py --limit 1   # 冒烟
  3. 生成 data/compare_A_*.json 和 compare_B_*.json 两份回答文件
     → 把两份都贴给裁判盲评（文件名不含型号，裁判不知道谁是谁）

常用端点速查：
  oMLX本地    http://127.0.0.1:8000/v1
  LM Studio   http://localhost:1234/v1
  Ollama      http://localhost:11434/v1
  DeepSeek    https://api.deepseek.com/v1
  通义兼容    https://dashscope.aliyuncs.com/compatible-mode/v1
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

# ================== 在这里填两个模型 ==================
MODEL_A = {
    "api_base": "http://127.0.0.1:8000/v1",
    "api_key": "omlx-***REMOVED***",
    "model_name": "Qwen3.5-9B-MLX-4bit",
}
MODEL_B = {
    "api_base": "",          # 例: http://localhost:1234/v1
    "api_key": "",
    "model_name": "",        # 例: qwen3.8-27b-ud-iq3_xxs
}
# =====================================================

QUESTIONS = [
    {"id": "Q1", "type": "多跳对比", "q": "传唤和继续盘问有什么区别？各自的时限是多久？"},
    {"id": "Q2", "type": "否定排除", "q": "哪些人不适用继续盘问？"},
    {"id": "Q3", "type": "双档数字", "q": "行政案件立案审查期限是多久？疑难复杂案件呢？"},
    {"id": "Q4", "type": "全局综合", "q": "从受案到处罚决定，这份资料覆盖了办案的哪些主要环节？"},
    {"id": "Q5", "type": "改写桥接", "q": "行政拘留可以暂缓执行吗？需要提供担保人还是保证金？"},
]


def validate(cfg, label):
    if not cfg.get("api_base", "").startswith(("http://", "https://")):
        print(f"{label} 的 api_base 未填写或非法，请编辑脚本顶部配置块")
        sys.exit(1)
    if not cfg.get("model_name", "").strip():
        print(f"{label} 的 model_name 未填写")
        sys.exit(1)


def run_suite(svc, label, limit):
    results = []
    for item in QUESTIONS[:limit]:
        t0 = time.time()
        try:
            r = svc.answer_question(item["q"], user_id=1, tenant_id=1, clearance_level=5)
            answer = r.get("answer") or ""
            sources = [s if isinstance(s, int) else s.get("id") for s in r.get("source_documents", [])]
        except Exception as e:
            answer, sources = f"（调用失败: {str(e)[:120]}）", []
        dt = time.time() - t0
        results.append({
            "qid": item["id"], "type": item["type"], "question": item["q"],
            "answer": answer, "seconds": round(dt, 1), "cited_docs": sources,
        })
        print(f"  [{label}] {item['id']} {item['type']} {dt:.0f}s 答案{len(answer)}字")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="题数上限（默认5）")
    args = ap.parse_args()

    validate(MODEL_A, "MODEL_A")
    validate(MODEL_B, "MODEL_B")

    from application.services.rag_service import get_rag_service, LLM_CONFIG
    svc = get_rag_service()
    original = dict(LLM_CONFIG)   # 跑完恢复原配置，不影响线上

    out_dir = os.path.join(SERVER_DIR, "data")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary = {}
    try:
        for label, cfg in (("A", MODEL_A), ("B", MODEL_B)):
            print(f"=== 样本{label}：{cfg['model_name']} @ {cfg['api_base']} ===")
            svc.hot_swap_llm(cfg)   # 热切换并清缓存，两模型互不串味
            results = run_suite(svc, label, args.limit)
            summary[label] = {
                "avg_seconds": round(sum(r["seconds"] for r in results) / len(results), 1),
                "results": results,
            }
    finally:
        LLM_CONFIG.update(original)
        try:
            svc.cache_manager.clear_all()
        except Exception:
            pass
        print("已恢复原模型配置")

    for label in ("A", "B"):
        path = os.path.join(out_dir, f"compare_{label}_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sample": label, **summary[label]}, f, ensure_ascii=False, indent=2)
        print(f"样本{label} 回答文件: {path}")

    print(f"\n平均耗时: A={summary['A']['avg_seconds']}s | B={summary['B']['avg_seconds']}s")
    print("把两份 compare_*.json 一起贴给裁判盲评（文件名不含型号）")


if __name__ == "__main__":
    main()
