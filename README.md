# 企业知识库智能问答系统（RAG）

> 混合检索 + 多模型热插拔 + 评测驱动的企业级 RAG 问答系统
> Python · Flask · Vue3 · LangChain · ChromaDB · BM25(jieba) · Cross-Encoder · 本地化大模型(Qwen3)

## 架构

```
用户提问
   │
   ▼
① 缓存层 ──── 命中 → 直接返回（<1s）
   │ 未命中
② 理解层 ──── 查询改写（指代消解 + 多变体扩展 + 领域同义规则，带缓存保证确定性）
   │
③ 检索层 ──── 稠密路(Embedding→Chroma) ─┐
   │                                     ├→ RRF融合 → Cross-Encoder重排
   │        稀疏路(jieba→BM25) ───────────┘        → 置信度兜底 → 动态TopK
   │                                              → 父窗口扩展（子块命中、父段落作答）
④ 生成层 ──── 提示词模板 → LLM流式生成(SSE)
   │
⑤ 落地层 ──── 问答历史 → 语义缓存回写 → 点赞/点踩反馈 → badcase转化金标
```

## 核心特性

- **混合检索**：BM25（词法精确）+ 向量（语义泛化）双路召回，RRF 倒数排名融合，Cross-Encoder 精排——单路故障时另一路自动兜底
- **父子索引**：小子块精准匹配、父窗口完整作答，兼顾检索精度与上下文完整性
- **多租户 + 密级 + ACL**：部门隔离、密级门槛、显式授权三级可见性控制，权限元数据双库同步
- **模型热插拔**：LLM/嵌入模型经注册表运行时切换（OpenAI 兼容协议），切换自动清理语义缓存
- **评测驱动**：57 题双粒度金标集（文档级 Recall + 章节级关键词命中）+ LLM-as-Judge A/B 盲评框架（位置随机化防偏）
- **质量闭环**：点赞/点踩 → badcase 自动转化金标候选 → 同义规则引擎修复检索缺口

## 评测结果

| 指标 | 数值 | 说明 |
|---|---|---|
| Recall@5 | **1.000** | 57 题四领域金标集 |
| MRR@5 | **1.000** | |
| 章节关键词命中率 | **0.944+** | 单文档 1323 块场景下的章节级区分指标 |
| LLM A/B 盲评 | 9B 本地 vs 27B 量化：99.3 vs 95.3（200分制） | 陷阱题（无答案识别）为决定性维度 |

## 性能剖析（Prometheus + Locust 实测）

全链路延迟拆解（Locust 20 并发压测 + `/metrics` 埋点采样）：

| 检索阶段 | P50 | P95 | 说明 |
|----------|-----|-----|------|
| BM25 词法召回 | **10ms** | 50ms | jieba 分词 + 倒排 |
| RRF 倒数排名融合 | **10ms** | 10ms | 双路合并 |
| Vector 稠密召回 | ~2s | >10s | 含 embedding API 调用，受本地端点波动影响 |
| Cross-Encoder 重排 | **1s** | 2s | BAAI/bge-reranker 精排 |
| **检索全链路** | **~3s** | — | 相对生成可忽略 |
| **LLM 生成** | **≥30s** | 169s | 硬件/网络受限，决定性长杆 |

**结论**：检索与重排全链路在秒级内完成，端到端 TTFT 的长杆是本地大模型生成（本地 9B / 局域网 27B 算力受限），而非 RAG 管线。优化方向为语义缓存命中（热点问题跳过检索+生成）、模型量化/蒸馏、流式首 token 优先返回。

详见 [`docs/interview_prep.md`](docs/interview_prep.md)。

## 快速开始

```bash
# 1. 依赖（Python 3.12 venv）
pip install -r server/requirements.txt

# 2. 配置：复制 server/.env.example → server/.env 填入本地模型端点
# 3. 初始化数据库
mysql -u root -p db_enterprise_9a < server/scripts/init_database.sql

# 4. 灌入演示语料并启动
cd server
python scripts/seed_sample_docs.py
python app.py

# 5. 前端
cd client && npm install && npm run dev
```

## 工程实践

- **评测驱动重构**：1416 行核心服务拆分为 8 个单一职责模块，以 57 题评测作为安全网实现零行为变更迁移
- **33 项单元测试**：覆盖 RRF 融合、分块页码贯通、密码双算法迁移、查询改写缓存确定性、OCR 断行修复
- **OCR 断行修复**：CJK 空白规范化解决扫描件换行导致的"检索/评测/验证同时失明"问题
- **22+ 规范 commit**（feat/fix/refactor/test 分明），历史经 git-filter-repo 密钥清洗

## 免责

本项目为个人学习/演示用途。演示语料（公安执法考试资料等）仅用于技术验证，不代表任何官方立场。
