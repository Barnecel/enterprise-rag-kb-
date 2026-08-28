# -*- coding: utf-8 -*-
from locust import HttpUser, task, between, constant
import random
import os

QUESTIONS = [
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

class RAGUser(HttpUser):
    wait_time = constant(0.5)  # 固定 0.5s 间隔，别随机
    token = None

    def on_start(self):
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("data", {}).get("token") or data.get("token")
            print(f"[User {id(self)}] Login OK, token={self.token[:10]}...")
        else:
            print(f"[User {id(self)}] Login FAILED: {resp.status_code} {resp.text}")

    @task(10)
    def ask_question(self):
        if not self.token:
            print(f"[User {id(self)}] No token, skipping")
            return
        q = random.choice(QUESTIONS)
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.post("/api/qa/ask", json={"question": q}, headers=headers, 
                              name="/api/qa/ask", catch_response=True) as resp:
            print(f"[User {id(self)}] Ask status={resp.status_code}")
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:100]}")
            else:
                data = resp.json()
                if data.get('code') != 200:
                    resp.failure(f"API {data.get('code')}: {data.get('message')}")

    @task(1)
    def health_check(self):
        self.client.get("/api/health", name="/api/health")

    @task(1)
    def metrics_check(self):
        self.client.get("/metrics", name="/metrics")
