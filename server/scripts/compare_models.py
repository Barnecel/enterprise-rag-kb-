# -*- coding: utf-8 -*-
"""
模型 A/B 对比测试 v3 —— 题库驱动 + N次重复 + 自动裁判
用方法：
  1. 改下面 MODEL_A / MODEL_B（直填URL）
  2. 可选：填 JUDGE（一个更强的裁判模型，如 DeepSeek）实现自动打分；
     不填则只生成回答文件，人工/贴给裁判评
  3. ../.venv/bin/python scripts/compare_models.py            # 20题×1次
     ../.venv/bin/python scripts/compare_models.py --repeats 3 # 20题×3次（推荐）
     --types 多跳对比,数字期限   # 只跑指定类型
     --limit N                  # 只跑前N题
产出：
  data/compare_A_*.json / compare_B_*.json   回答原文（盲评格式）
  data/judge_scores_*.json                   裁判逐题打分（若配置JUDGE）
  控制台：总分/分题型均值/配对差统计
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

# ================== 候选模型（直填URL，填几个测几个；只填一个=单模型模式） ==================
MODEL_A = {
    "api_base": "http://192.168.10.146:8080/v1",          # 例: http://localhost:1234/v1
    "api_key": "",
    "model_name": "qwen3.8-27b-coldfusion",        # 例: qwen3.8-27b-ud-iq3_xxs
}
MODEL_B = {
    "api_base": "",          # 留空=不测；例: http://127.0.0.1:8000/v1
    "api_key": "",           # 例: omlx-***REMOVED***
    "model_name": "",        # 例: Qwen3.5-9B-MLX-4bit
}
# ================== 裁判模型（可选，留空则不自动打分） ==================
JUDGE = {
    # "api_base": "https://api.deepseek.com/v1",
    # "api_key": "sk-xxx",
    # "model_name": "deepseek-chat",
}
# =====================================================

BANK_PATH = os.path.join(SERVER_DIR, "scripts", "question_bank.json")

RUBRIC = """你是严格的RAG问答评审。依据【评分要点】对两份回答独立打分（两回答顺序已随机，勿假设先后优劣）。
维度与满分：忠实准确4（与要点矛盾或编造语料外事实扣）、抗幻觉2（要点标注"语料未覆盖"时，正确行为是明确说明未提及，编造则0分）、要点完整2、条理清晰1、引用来源1。
只依据给定要点与基本法律逻辑，不要引入你自己的知识加分。
严格输出JSON（不要多余文字）：
{"回答1":{"忠实":0-4,"抗幻觉":0-2,"完整":0-2,"条理":0-1,"引用":0-1,"total":0-10,"评语":"一句话"},"回答2":{...},"更优":"回答1|回答2|平手"}"""


def validate(cfg, label):
    if not cfg.get("api_base", "").startswith(("http://", "https://")):
        print(f"{label} 的 api_base 未填写或非法")
        sys.exit(1)
    if not cfg.get("model_name", "").strip():
        print(f"{label} 的 model_name 未填写")
        sys.exit(1)


def filled(cfg):
    return bool(cfg.get("api_base", "").startswith(("http://", "https://"))
                and cfg.get("model_name", "").strip())


def run_suite(svc, label, questions, repeats):
    results = []
    total = len(questions) * repeats
    done = 0
    for item in questions:
        for rep in range(1, repeats + 1):
            t0 = time.time()
            try:
                r = svc.answer_question(item["q"], user_id=1, tenant_id=1, clearance_level=5)
                answer = r.get("answer") or ""
                sources = [s if isinstance(s, int) else s.get("id") for s in r.get("source_documents", [])]
            except Exception as e:
                answer, sources = f"（调用失败: {str(e)[:120]}）", []
            dt = round(time.time() - t0, 1)
            done += 1
            results.append({
                "qid": item["id"], "type": item["type"], "rep": rep,
                "question": item["q"], "answer": answer,
                "seconds": dt, "cited_docs": sources,
            })
            print(f"  [{label}] {item['id']} r{rep} {dt:.0f}s {len(answer)}字  ({done}/{total})")
    return results


def call_judge(judge, question, reference, trap, ans1, ans2):
    """让裁判模型对一对回答打分。返回解析后的dict或None"""
    import requests
    trap_note = "\n【本题是陷阱题】评分要点描述的是语料未覆盖的情况，回答若编造规则应给抗幻觉0分。" if trap else ""
    prompt = (f"【问题】{question}\n【评分要点】{reference}{trap_note}\n"
              f"【回答1】\n{ans1[:3000]}\n【回答2】\n{ans2[:3000]}\n\n{RUBRIC}")
    try:
        resp = requests.post(
            f"{judge['api_base']}/chat/completions",
            headers={"Authorization": f"Bearer {judge['api_key'] or 'dummy'}"},
            json={"model": judge["model_name"], "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}], "max_tokens": 800},
            timeout=120)
        text = resp.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {"error": text[:200]}
    except Exception as e:
        return {"error": str(e)[:160]}


RUBRIC_SINGLE = """你是严格的RAG问答评审。依据【评分要点】对这份回答独立打分。
维度与满分：忠实准确4（与要点矛盾或编造语料外事实扣）、抗幻觉2（要点标注"语料未覆盖"时，正确行为是明确说明未提及，编造则0分）、要点完整2、条理清晰1、引用来源1。
只依据给定要点与基本法律逻辑，不要引入你自己的知识加分。
严格输出JSON（不要多余文字）：
{"忠实":0-4,"抗幻觉":0-2,"完整":0-2,"条理":0-1,"引用":0-1,"total":0-10,"评语":"一句话"}"""


def call_judge_single(judge, question, reference, trap, answer):
    """单模型绝对分评分（无对比对象）"""
    import requests
    trap_note = "\n【本题是陷阱题】评分要点描述的是语料未覆盖的情况，回答若编造规则应给抗幻觉0分。" if trap else ""
    prompt = (f"【问题】{question}\n【评分要点】{reference}{trap_note}\n"
              f"【回答】\n{answer[:3000]}\n\n{RUBRIC_SINGLE}")
    try:
        resp = requests.post(
            f"{judge['api_base']}/chat/completions",
            headers={"Authorization": f"Bearer {judge['api_key'] or 'dummy'}"},
            json={"model": judge["model_name"], "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}], "max_tokens": 400},
            timeout=120)
        text = resp.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {"error": text[:200]}
    except Exception as e:
        return {"error": str(e)[:160]}


def aggregate(results, questions_meta):
    """总分与分题型统计"""
    meta = {q["id"]: q for q in questions_meta}
    by_type = {}
    totals = []
    for r in results:
        if not r.get("judge_total"):
            continue
        totals.append(r["judge_total"])
        by_type.setdefault(r["type"], []).append(r["judge_total"])
    out = {
        "judged": len(totals),
        "mean_total": round(sum(totals) / len(totals), 2) if totals else None,
        "by_type": {k: round(sum(v) / len(v), 2) for k, v in sorted(by_type.items())},
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="只跑前N题（0=全部）")
    ap.add_argument("--types", default="", help="逗号分隔的题型过滤")
    args = ap.parse_args()

    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)["questions"]
    if args.types:
        allow = set(args.types.split(","))
        bank = [q for q in bank if q["type"] in allow]
    if args.limit:
        bank = bank[:args.limit]
    print(f"题库: {len(bank)} 题 × {args.repeats} 次 × 2 模型")

    models = []
    for label, cfg in (("A", MODEL_A), ("B", MODEL_B)):
        if filled(cfg):
            validate(cfg, f"MODEL_{label}")
            models.append((label, cfg))
    if not models:
        print("MODEL_A / MODEL_B 至少填写一个")
        sys.exit(1)
    if len(models) == 1:
        print(f"单模型模式：仅测样本{models[0][0]}，输出该模型的回答与绝对分评分")

    from application.services.rag_service import get_rag_service, LLM_CONFIG
    svc = get_rag_service()
    original = dict(LLM_CONFIG)

    out_dir = os.path.join(SERVER_DIR, "data")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {}
    try:
        for label, cfg in models:
            print(f"=== 样本{label}: {cfg['model_name']} ===")
            svc.hot_swap_llm(cfg)
            summary[label] = run_suite(svc, label, bank, args.repeats)
    finally:
        LLM_CONFIG.update(original)
        try:
            svc.cache_manager.clear_all()
        except Exception:
            pass
        print("已恢复原模型配置")

    # 保存回答文件（盲评格式）
    for label in summary:   # 单模型模式下只存在已测的标签
        path = os.path.join(out_dir, f"compare_{label}_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sample": label, "results": summary[label]}, f, ensure_ascii=False, indent=2)
        print(f"样本{label} 回答: {path}")

    # 自动裁判（可选）
    if JUDGE.get("api_base"):
        ref_of = {q["id"]: q for q in bank}
        judge_out = []
        if len(models) == 2:
            print("=== 裁判打分中（双模型配对，含位置随机化） ===")
            rng = random.Random(42)
            for label in ("A", "B"):
                for r in summary[label]:
                    r["judge_total"] = None
            for i in range(len(summary["A"])):
                ra, rb = summary["A"][i], summary["B"][i]
                pair = [(ra, "回答1"), (rb, "回答2")]
                if rng.random() < 0.5:
                    pair = list(reversed(pair))
                qmeta = ref_of[ra["qid"]]
                verdict = call_judge(JUDGE, ra["question"], qmeta["reference"],
                                     qmeta["trap"], pair[0][0]["answer"], pair[1][0]["answer"])
                for ans_obj, slot in pair:
                    if isinstance(verdict, dict) and slot in verdict:
                        s = verdict[slot]
                        ans_obj["judge_total"] = s.get("total")
                        ans_obj["judge_comment"] = s.get("评语", "")
                judge_out.append({"qid": ra["qid"], "rep": ra["rep"], "verdict": verdict})
            jpath = os.path.join(out_dir, f"judge_scores_{ts}.json")
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(judge_out, f, ensure_ascii=False, indent=2)
            print(f"裁判打分: {jpath}")
            agg_a = aggregate(summary["A"], bank)
            agg_b = aggregate(summary["B"], bank)
            print(f"\n===== 总分: A={agg_a['mean_total']} B={agg_b['mean_total']} (各{agg_a['judged']}次评分) =====")
            print(f"分题型: A={agg_a['by_type']}")
            print(f"        B={agg_b['by_type']}")
            deltas = [(ra.get('judge_total') or 0) - (rb.get('judge_total') or 0)
                      for ra, rb in zip(summary['A'], summary['B'])]
            wins = sum(1 for d in deltas if d > 0); losses = sum(1 for d in deltas if d < 0)
            print(f"配对胜负: A胜{wins} / B胜{losses} / 平{len(deltas)-wins-losses} | 平均分差 {sum(deltas)/len(deltas):+.2f}")
        else:
            label = models[0][0]
            print(f"=== 裁判绝对分评分中（单模型：{label}） ===")
            for r in summary[label]:
                qmeta = ref_of[r["qid"]]
                verdict = call_judge_single(JUDGE, r["question"], qmeta["reference"],
                                            qmeta["trap"], r["answer"])
                if isinstance(verdict, dict) and "total" in verdict:
                    r["judge_total"] = verdict.get("total")
                    r["judge_comment"] = verdict.get("评语", "")
                judge_out.append({"qid": r["qid"], "rep": r["rep"], "verdict": verdict})
            jpath = os.path.join(out_dir, f"judge_scores_{ts}.json")
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(judge_out, f, ensure_ascii=False, indent=2)
            print(f"裁判打分: {jpath}")
            agg = aggregate(summary[label], bank)
            print(f"\n===== 平均总分: {agg['mean_total']} (共{agg['judged']}次评分) =====")
            print(f"分题型: {agg['by_type']}")
    else:
        print("未配置JUDGE，跳过自动打分。把 compare_*.json 贴给裁判人工/LLM盲评。")


if __name__ == "__main__":
    main()
