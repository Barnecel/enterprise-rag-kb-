# -*- coding: utf-8 -*-
"""
RAG 系统压测脚本
运行: locust -f loadtest/locustfile.py --host=http://localhost:5000 --users=50 --spawn-rate=5 --run-time=5m --headless --csv=results
"""
from locust import HttpUser, task, between
import random
import os

# 从金标集读取问题，或使用内置列表
GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), '..', 'server', 'scripts', 'golden_set.jsonl')

def load_questions():
    questions = []
    if os.path.exists(GOLDEN_SET_PATH):
        with open(GOLDEN_SET_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    import json
                    item = json.loads(line.strip())
                    if 'question' in item:
                        questions.append(item['question'])
                except Exception:
                    continue
    # 兜底问题
    if not questions:
        questions = [
            "公司年假有几天？",
            "迟到超过30分钟视为旷工吗？",
            "什么是密级门槛？",
            "如何申请跨部门协作？",
            "公文写作规范是什么？",
            "保密制度有哪些规定？",
            "会议纪要怎么写？",
            "请假流程是怎样的？",
            "差旅报销标准？",
            "印章使用管理规定？",
        ]
    return questions

QUESTIONS = load_questions()

# 登录获取 token（需先有测试账号）
def login(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("token")
    return None

class RAGUser(HttpUser):
    wait_time = between(0.5, 2)
    token = None

    def on_start(self):
        """每个虚拟用户启动时登录"""
        self.token = login(self.client)
        if not self.token:
            print("⚠️ 登录失败，请检查测试账号是否存在")

    @task(10)
    def ask_question(self):
        """核心问答接口"""
        if not self.token:
            return
        q = random.choice(QUESTIONS)
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client.post("/api/qa/ask", json={"question": q}, headers=headers, name="/api/qa/ask")

    @task(3)
    def ask_stream(self):
        """流式问答接口"""
        if not self.token:
            return
        q = random.choice(QUESTIONS)
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.post("/api/qa/ask/stream", json={"question": q}, headers=headers, 
                              name="/api/qa/ask/stream", catch_response=True, stream=True) as resp:
            # 消费流式响应
            for _ in resp.iter_lines():
                pass

    @task(1)
    def health_check(self):
        """健康检查"""
        self.client.get("/api/health", name="/api/health")

    @task(1)
    def metrics_check(self):
        """Prometheus metrics 端点"""
        self.client.get("/metrics", name="/metrics")
