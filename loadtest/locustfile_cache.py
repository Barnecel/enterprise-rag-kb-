# -*- coding: utf-8 -*-
"""缓存命中率专用压测：固定问同一道题，触发 L1/L2/L3 缓存"""
from locust import HttpUser, task, constant
import random

FIXED_Q = "公司年假有几天？"

class CacheUser(HttpUser):
    wait_time = constant(0.2)
    token = None

    def on_start(self):
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            self.token = resp.json().get("data", {}).get("token")

    @task
    def ask_same(self):
        if not self.token:
            return
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client.post("/api/qa/ask", json={"question": FIXED_Q}, headers=headers, name="/api/qa/ask(fixed)")
