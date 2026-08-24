# -*- coding: utf-8 -*-
"""
RAG服务模块 - LangChain核心集成
提供检索增强生成(RAG)功能，整合5大高级检索特性：
1. 混合检索：BM25稀疏 + Embedding稠密 + RRF融合 + Cross-Encoder重排
2. 父子索引：小子块检索、父窗口作答
3. 动态TopK：基于分数分布动态调整召回数量
4. 查询改写：LLM生成多查询变体
5. 租户隔离：按部门(tenant_id)过滤文档与元数据
集成oMLX API (http://127.0.0.1:8000/v1)
"""

import os
import json
import pickle
import shutil
import threading
import time
from typing import List, Dict, Any, Iterator, Optional

import requests

from utils.logger_handler import logger
from utils.config_handler import config
from utils.prompt_loader import load_rag_prompt, build_dialogue_text

from application.services.chunking import build_parent_child_chunks, build_parent_child_chunks_from_elements
from application.services.document_parser import parse_document
from application.services.bm25_retriever import BM25Retriever
from application.services.fusion import reciprocal_rank_fusion
from application.services.reranker import Reranker
from application.services.query_rewriter import QueryRewriter
from application.services.cache_manager import CacheManager

# 从YAML配置获取
LLM_CONFIG = config.get_section('llm')
EMBEDDING_CONFIG = config.get_section('embedding')
CHROMA_CONFIG = config.get_section('chroma')
RAG_CONFIG = config.get_section('rag')
DOCUMENT_CONFIG = config.get_section('document')

HYBRID_CONFIG = RAG_CONFIG.get('hybrid', {})
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
DYNAMIC_CONFIG = RAG_CONFIG.get('dynamic_topk', {})
QW_CONFIG = RAG_CONFIG.get('query_rewrite', {})
TENANT_CONFIG = RAG_CONFIG.get('tenant', {})
ENUM_CONFIG = RAG_CONFIG.get('enumeration', {})

# LangChain相关导入
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_community.document_loaders import TextLoader, PyPDFLoader
    LANCHAIN_AVAILABLE = True
except ImportError:
    LANCHAIN_AVAILABLE = False
    logger.warning("LangChain not installed. RAG functionality will be limited.")

# ============================================================
# 模块级共享状态（跨多个 RAGService 实例共享 BM25 索引与父窗口映射）
# ============================================================
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(SERVER_DIR, 'data')
PARENT_MAP_FILE = os.path.join(DATA_DIR, 'parent_map.pkl')

_bm25 = BM25Retriever()
_parent_map: Dict[str, str] = {}
_parent_lock = threading.Lock()

_rag_service_instance: Optional["RAGService"] = None
_rag_service_lock = threading.Lock()


def get_rag_service() -> "RAGService":
    """获取全局唯一的 RAGService 实例（线程安全，避免重复初始化 Chroma 客户端）"""
    global _rag_service_instance
    if _rag_service_instance is None:
        with _rag_service_lock:
            if _rag_service_instance is None:
                _rag_service_instance = RAGService()
    return _rag_service_instance


def _load_parent_map():
    """从磁盘加载父窗口映射"""
    global _parent_map
    if os.path.exists(PARENT_MAP_FILE):
        try:
            with open(PARENT_MAP_FILE, 'rb') as f:
                _parent_map = pickle.load(f) or {}
            logger.info(f"Parent map loaded from disk: {len(_parent_map)} entries")
        except Exception as e:
            logger.error(f"Failed to load parent map: {e}")
            _parent_map = {}


def _save_parent_map():
    """持久化父窗口映射"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PARENT_MAP_FILE, 'wb') as f:
            pickle.dump(_parent_map, f)
    except Exception as e:
        logger.error(f"Failed to save parent map: {e}")


def _write_parse_stats(doc_id: int, file_path: str, stats: dict) -> None:
    """追加解析统计到 server/data/parse_stats.jsonl（便于事后排查解析质量）"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        row = {'doc_id': doc_id, 'file': os.path.basename(file_path), 'time': __import__('datetime').datetime.now().isoformat(timespec='seconds'), **stats}
        with open(os.path.join(DATA_DIR, 'parse_stats.jsonl'), 'a', encoding='utf-8') as f:
            f.write(__import__('json').dumps(row, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.warning(f"write parse stats failed: {e}")


_load_parent_map()


class OMLXEmbeddings:
    """
    自定义嵌入类 - 通过oMLX API调用Qwen3-Embedding-8B-4bit-DWQ模型
    """

    def __init__(self, api_base: str, api_key: str, model_name: str):
        self.api_base = api_base
        self.api_key = api_key
        self.model_name = model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档

        Args:
            texts: 文档列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        try:
            response = requests.post(
                f"{self.api_base}/embeddings",
                headers={
                    'Authorization': f"Bearer {self.api_key}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.model_name,
                    'input': texts
                },
                timeout=120
            )
            if response.status_code == 200:
                result = response.json()
                return [item['embedding'] for item in result['data']]
            raise RuntimeError(f"Embedding API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        results = self.embed_documents([text])
        return results[0]

    def __call__(self, texts: List[str]) -> List[List[float]]:
        """使对象可调用"""
        return self.embed_documents(texts)


class RAGService:
    """
    RAG服务类 - 封装检索增强生成的核心逻辑
    """

    def __init__(self):
        """初始化RAG服务，加载向量库和LLM模型"""
        self.vectorstore = None
        self.embeddings = None
        self.bm25 = _bm25
        self.reranker = Reranker()
        self.query_rewriter = QueryRewriter()
        self.cache_manager = CacheManager()
        self._initialize_embeddings()
        self._initialize_vectorstore()

    def _initialize_embeddings(self):
        """
        初始化嵌入模型
        使用oMLX的Qwen3-Embedding-8B-4bit-DWQ
        """
        if not LANCHAIN_AVAILABLE:
            logger.warning("LangChain not available, using mock embeddings")
            self.embeddings = None
            return

        try:
            self.embeddings = OMLXEmbeddings(
                api_base=EMBEDDING_CONFIG['api_base'],
                api_key=LLM_CONFIG.get('api_key', 'dummy'),
                model_name=EMBEDDING_CONFIG['model_name']
            )
            logger.info(f"Embedding model initialized: {EMBEDDING_CONFIG['model_name']} at {EMBEDDING_CONFIG['api_base']}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            self.embeddings = None

    def _initialize_vectorstore(self):
        """
        初始化Chroma向量数据库
        """
        if not LANCHAIN_AVAILABLE or self.embeddings is None:
            return

        try:
            persist_dir = CHROMA_CONFIG['persist_directory']
            if os.path.exists(persist_dir):
                self.vectorstore = Chroma(
                    collection_name=CHROMA_CONFIG['collection_name'],
                    persist_directory=persist_dir,
                    embedding_function=self.embeddings
                )
                logger.info(f"Vector store loaded from: {persist_dir}")
            else:
                os.makedirs(persist_dir, exist_ok=True)
                logger.info(f"New vector store will be created at: {persist_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self.vectorstore = None

    # ============================================================
    # 文档加载与入库 (特性2: 父子索引 / 特性5: 租户元数据)
    # ============================================================
    def load_document(self, file_path: str) -> Optional[Any]:
        """
        加载文档文件

        Args:
            file_path: 文档文件路径

        Returns:
            Document: LangChain Document对象，失败返回None
        """
        if not LANCHAIN_AVAILABLE:
            return None

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.txt':
                loader = TextLoader(file_path, encoding='utf-8')
            elif ext == '.pdf':
                loader = PyPDFLoader(file_path)
            elif ext == '.md':
                loader = TextLoader(file_path, encoding='utf-8')
            elif ext in ('.doc', '.docx'):
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(file_path)
            else:
                logger.warning(f"Unsupported file type: {ext}")
                return None

            documents = loader.load()
            return documents[0] if documents else None
        except Exception as e:
            logger.error(f"Failed to load document: {e}")
            return None

    def split_document(self, document: Any) -> List[Any]:
        """
        将文档分割成小块(单层，兼容旧接口)

        Args:
            document: LangChain Document对象

        Returns:
            List[Document]: 分割后的文档块列表
        """
        if not LANCHAIN_AVAILABLE:
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=DOCUMENT_CONFIG['chunk_size'],
            chunk_overlap=DOCUMENT_CONFIG['chunk_overlap'],
            length_function=len
        )
        return text_splitter.split_documents([document])

    def add_document_to_vectorstore(
        self,
        file_path: str,
        doc_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
        doc_level: str = 'public',
        min_level: int = 1,
        owner_id: Optional[int] = None,
        progress_cb=None
    ) -> bool:
        """
        添加文档到向量库（父子索引 + BM25 + 父窗口映射）

        Args:
            file_path: 文档文件路径
            doc_id: 数据库文档ID(用于关联元数据，可空则自动反查)
            tenant_id: 所属租户ID
            doc_level: 文档级别(public/private)，写入块元数据供权限过滤
            min_level: 文档最低密级(1公开/2内部/3机密/4绝密)
            owner_id: 上传者用户ID(所有者恒可见)
            progress_cb: 可选 progress_cb(done_pages, total_pages) 解析进度回调

        Returns:
            bool: 是否成功
        """
        if not LANCHAIN_AVAILABLE or self.embeddings is None:
            logger.error("Cannot add document: LangChain or embeddings not available")
            return False

        try:
            # 反查文档ID、租户与权限字段
            if doc_id is None or tenant_id is None or min_level is None:
                from application.utils.db_utils import execute_query, execute_update
                rows = execute_query(
                    "SELECT id, tenant_id, doc_level, min_level, upload_by FROM tb_document WHERE file_path = %s LIMIT 1",
                    (file_path,)
                )
                if rows:
                    doc_id = doc_id or rows[0]['id']
                    tenant_id = tenant_id or rows[0]['tenant_id']
                    doc_level = doc_level or rows[0].get('doc_level') or 'public'
                    min_level = min_level if min_level is not None else (rows[0].get('min_level') or 1)
                    owner_id = owner_id if owner_id is not None else rows[0].get('upload_by')

            if doc_id is None:
                logger.error(f"Cannot resolve doc_id for {file_path}")
                return False
            tenant_id = tenant_id or 1
            doc_level = doc_level or 'public'
            min_level = min_level or 1

            # 复杂文档解析（text/table/image 元素流，永不抛异常，失败降级）
            elements, stats = parse_document(file_path, progress_cb=progress_cb)
            if not elements:
                logger.error(f"Document {doc_id} parsed to empty elements: {stats.get('warnings')}")
                return False
            _write_parse_stats(doc_id, file_path, stats)

            # 生成文本预览（全文），写入 tb_document.content 供前端详情/全文阅读
            # 列已升级 MEDIUMTEXT(16MB)；保留 400万字符安全上限防极端文件
            from application.utils.db_utils import execute_update
            preview = '\n'.join(e.text for e in elements if e.kind in ('text', 'table') and e.text).strip()
            if preview:
                try:
                    execute_update(
                        "UPDATE tb_document SET content = %s WHERE id = %s",
                        (preview[:4_000_000], doc_id)
                    )
                except Exception as e:
                    logger.warning(f"Failed to update content preview for doc {doc_id}: {e}")

            # 元素化父子分块（表格单元不切断，父窗口内联完整表格）
            child_chunks, parent_map = build_parent_child_chunks_from_elements(
                elements,
                doc_id=doc_id,
                source=os.path.basename(file_path),
                tenant_id=tenant_id,
                doc_level=doc_level,
                min_level=min_level,
                owner_id=owner_id
            )
            if not child_chunks:
                logger.warning("No chunks created from document elements")
                return False

            logger.info(f"Document {doc_id} parsed {len(elements)} elements -> {len(child_chunks)} child chunks"
                        f" (tables={stats['table_count']}, images={stats['image_count']}, ocr_pages={stats['ocr_pages']})")

            # 添加到Chroma向量库（分批嵌入：整包提交会让嵌入服务掐断连接）
            EMB_BATCH = int(RAG_CONFIG.get('embed_batch_size', 16))
            total_chunks = len(child_chunks)

            def _embed_progress(done: int, stage: str):
                if progress_cb:
                    try:
                        progress_cb(done, total_chunks, stage)
                    except Exception:
                        pass

            if self.vectorstore is None:
                persist_dir = CHROMA_CONFIG['persist_directory']
                os.makedirs(persist_dir, exist_ok=True)
                first = child_chunks[:EMB_BATCH]
                _embed_progress(len(first), 'embed')
                self.vectorstore = Chroma.from_documents(
                    documents=first,
                    embedding=self.embeddings,
                    collection_name=CHROMA_CONFIG['collection_name'],
                    persist_directory=persist_dir
                )
                rest = child_chunks[EMB_BATCH:]
            else:
                rest = child_chunks

            for i in range(0, len(rest), EMB_BATCH):
                part = rest[i:i + EMB_BATCH]
                try:
                    self.vectorstore.add_documents(part)
                except Exception:
                    # 单批失败降级重试一次（更小粒度），仍失败则抛出让上层标记failed
                    time.sleep(2)
                    for j in range(i, min(i + EMB_BATCH, len(rest)), max(1, EMB_BATCH // 4)):
                        self.vectorstore.add_documents(rest[j:j + max(1, EMB_BATCH // 4)])
                _embed_progress(min(i + EMB_BATCH, total_chunks), 'embed')

            # 更新BM25索引与父窗口映射
            self.bm25.add_chunks(child_chunks)
            global _parent_map
            with _parent_lock:
                _parent_map.update(parent_map)
                _save_parent_map()

            logger.info(f"Document added to vector store: {file_path} (tenant={tenant_id})")
            self.cache_manager.clear_all()
            return True
        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            import traceback
            traceback.print_exc()
            return False

    def delete_document_from_vectorstore(self, doc_id) -> bool:
        """
        从向量库移除某文档的全部数据（Chroma + BM25 + 父窗口映射）。

        Args:
            doc_id: 数据库文档ID

        Returns:
            bool: 是否成功（无残留块即视为成功）
        """
        try:
            # 确保 Chroma 已加载（未初始化时从磁盘加载，保证磁盘集合被清理）
            if self.vectorstore is None:
                self._initialize_vectorstore()
            if self.vectorstore is not None:
                try:
                    self.vectorstore.delete(where={'doc_id': doc_id})
                    logger.info(f"Chroma deleted doc {doc_id} chunks")
                except Exception as e:
                    logger.error(f"Chroma delete doc {doc_id} failed: {e}")
            else:
                logger.warning(f"Vector store unavailable, skip Chroma delete for doc {doc_id}")

            # BM25 移除 + 父窗口映射清理
            removed_parents = self.bm25.remove_doc(doc_id)
            global _parent_map
            with _parent_lock:
                for pid in removed_parents:
                    _parent_map.pop(pid, None)
                _save_parent_map()

            logger.info(f"Document {doc_id} removed from vector store ({len(removed_parents)} parents)")
            self.cache_manager.clear_all()
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id} from vector store: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ============================================================
    # 混合检索管线 (特性1/3/4/5)
    # ============================================================
    def _dense_search(
        self,
        query: str,
        tenant_id: Optional[int],
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """稠密检索(Embedding + Chroma)，带租户/密级/ACL过滤"""
        if not LANCHAIN_AVAILABLE or self.vectorstore is None:
            return []

        try:
            dense_top_k = int(HYBRID_CONFIG.get('dense_top_k', 20))
            filter_dict = None
            if tenant_id is not None:
                # 可见性：同部门+公开+密级达标 OR 所有者 OR 显式授权(覆盖部门/密级)
                or_clauses = [
                    {"$and": [
                        {"tenant_id": {"$eq": tenant_id}},
                        {"doc_level": {"$eq": "public"}},
                        {"min_level": {"$lte": clearance_level or 1}}
                    ]},
                    {"owner_id": {"$eq": user_id}},
                ]
                if acl_doc_ids:
                    or_clauses.append({"doc_id": {"$in": acl_doc_ids}})
                filter_dict = {"$or": or_clauses}

            results = self.vectorstore.similarity_search_with_score(
                query,
                k=dense_top_k,
                filter=filter_dict
            )

            candidates = []
            for doc, score in results:
                # Chroma返回L2距离，超过阈值视为不相关
                if score > RAG_CONFIG['score_threshold']:
                    continue
                meta = doc.metadata
                candidates.append({
                    'doc_id': meta.get('doc_id'),
                    'parent_id': meta.get('parent_id'),
                    'source': meta.get('source', ''),
                    'tenant_id': meta.get('tenant_id', 1),
                    'chunk_index': meta.get('chunk_index', 0),
                    'text': doc.page_content,
                    'score': float(score),        # L2距离(越小越相关)
                    'dense_score': float(score),
                })
            return candidates
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            return []

    def _hybrid_retrieve(
        self,
        query: str,
        tenant_id: Optional[int],
        requested_top_k: int,
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> tuple:
        """
        完整混合检索管线
        查询改写 -> 双路召回(BM25+稠密) -> RRF融合 -> Cross-Encoder重排 -> 动态TopK -> 父窗口扩展

        Args:
            query: 查询文本
            tenant_id: 租户过滤(admin传None可见全部)
            requested_top_k: 请求的返回数量
            user_id: 查询用户ID(所有者恒可见)
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(用于查询改写时指代消解)

        Returns:
            (docs, stats)
        """
        stats = {'rewritten_queries': [], 'dense_count': 0, 'sparse_count': 0, 'topk_used': requested_top_k}

        # 1. 查询改写（结合历史消解指代）
        rewritten = self.query_rewriter.rewrite(query, history=history)
        stats['rewritten_queries'] = rewritten

        # 2. 对每个改写变体执行双路召回+RRF融合
        variant_candidates = []
        hybrid_enabled = HYBRID_CONFIG.get('enabled', True)
        dense_top_k = int(HYBRID_CONFIG.get('dense_top_k', 20))
        bm25_top_k = int(HYBRID_CONFIG.get('bm25_top_k', 20))
        rrf_k = int(HYBRID_CONFIG.get('rrf_k', 60))
        weights = HYBRID_CONFIG.get('weights', {'dense': 1.0, 'sparse': 1.0})

        for q in rewritten:
            dense = self._dense_search(q, tenant_id, user_id, clearance_level, acl_doc_ids) if hybrid_enabled else []
            sparse = self.bm25.search(q, bm25_top_k, tenant_id, user_id, clearance_level, acl_doc_ids) if hybrid_enabled else []
            stats['dense_count'] += len(dense)
            stats['sparse_count'] += len(sparse)

            if not dense and not sparse:
                continue
            fused = reciprocal_rank_fusion(dense, sparse, k=rrf_k, weights=weights)
            variant_candidates.append(fused)

        # 3. 合并多个改写变体的候选
        merged = self._merge_variants(variant_candidates)
        stats['fused_count'] = len(merged)

        if not merged:
            return [], stats

        # 4. Cross-Encoder重排 (rerank内部惰性加载，模型不可用自动降级为融合排序)
        fusion_top_n = int(HYBRID_CONFIG.get('fusion_top_n', 15))
        rerank_top_n = int(RERANK_CONFIG.get('top_n', 8))
        if RERANK_CONFIG.get('enabled', True):
            merged = self.reranker.rerank(query, merged[:fusion_top_n], rerank_top_n)
            stats['rerank_count'] = len(merged)
            # 重排置信度兜底：低于阈值的块不送LLM，防无关块靠词面overlap混入
            min_norm = float(RERANK_CONFIG.get('min_norm', 0.0))
            if min_norm > 0 and merged:
                pre_merged = merged
                merged = [c for c in merged if (c.get('rerank_norm') or 0) >= min_norm]
                if not merged:
                    merged = pre_merged[:1]  # 全部低于阈值则保留最优，避免空上下文
        else:
            merged = merged[:rerank_top_n]
            stats['rerank_count'] = len(merged)

        # 5. 动态TopK
        norm_scores = [self._norm_score(c) for c in merged]
        topk = self._select_dynamic_topk(norm_scores, requested_top_k)
        stats['topk_used'] = topk
        top = merged[:topk]

        # 6. 父窗口扩展
        docs = [self._to_output_doc(c) for c in top]

        # 7. 枚举/清单类查询：标题级匹配补充（根治"有哪些文档"类问题）
        if ENUM_CONFIG.get('enabled', True):
            try:
                pseudo = self._enumeration_docs(query, requested_top_k, tenant_id, user_id, clearance_level, acl_doc_ids)
            except Exception as e:
                logger.warning(f"Enumeration docs failed: {e}")
                pseudo = []
            if pseudo:
                pseudo_ids = {p.get('id') for p in pseudo}
                docs = pseudo + [d for d in docs if d.get('id') not in pseudo_ids]
                stats['enum_docs'] = len(pseudo)
                logger.info(f"Enumeration query matched {len(pseudo)} docs by title: '{query}'")

        # 8. 补全文档标题（供前端参考文档展示）
        try:
            doc_ids = [d.get('id') for d in docs if d.get('id')]
            if doc_ids:
                from application.utils.db_utils import execute_query
                placeholders = ','.join(['%s'] * len(doc_ids))
                rows = execute_query(
                    f"SELECT id, title FROM tb_document WHERE id IN ({placeholders})", doc_ids
                )
                title_map = {r['id']: r['title'] for r in rows}
                for d in docs:
                    d['title'] = title_map.get(d.get('id'))
        except Exception as e:
            logger.warning(f"Enrich doc titles failed: {e}")

        return docs, stats

    def _enumeration_docs(
        self,
        query: str,
        requested_top_k: int,
        tenant_id: Optional[int],
        user_id: Optional[int],
        clearance_level: Optional[int],
        acl_doc_ids: Optional[List[int]]
    ) -> List[Dict[str, Any]]:
        """
        枚举/清单类查询的标题级匹配（"技术文档有哪些" / "列出所有文档"）
        检测到枚举意图后，按标题 LIKE 检索用户可见文档，作为高优先级候选返回。
        无标题匹配时回退为列出全部可见文档，让LLM如实作答而非编造。
        """
        import re
        intent = re.search(r'有哪些|有什么|列出|列举|清单|全部|所有|多少(个|份|类|种|篇)|都有什么|包含哪些', query)
        if not intent:
            return []

        # 提取内容关键词（去掉意图词与通用词）
        keyword = re.sub(
            r'有哪些|有什么|列出|列举|清单|请|帮我|帮|都|什么|多少(个|份|类|种|篇)'
            r'|文档|资料|文件|知识库|请问|关于|内容|类型|标题',
            '', query
        ).strip()
        keyword = keyword[:20]
        limit = max(int(ENUM_CONFIG.get('max_docs', 15)), requested_top_k or 5)

        from application.utils.db_utils import execute_query
        if tenant_id is None:
            sql = ("SELECT id, title, content, tenant_id, doc_level, min_level "
                   "FROM tb_document WHERE status = 'completed'")
            params: tuple = ()
        else:
            sql = ("SELECT id, title, content, tenant_id, doc_level, min_level "
                   "FROM tb_document "
                   "WHERE status = 'completed' "
                   "AND ((tenant_id = %s AND doc_level = 'public' AND min_level <= %s) "
                   "OR upload_by = %s "
                   "OR id IN (SELECT document_id FROM tb_document_acl WHERE user_id = %s))")
            params = (tenant_id, clearance_level or 1, user_id, user_id)

        base_params = params
        if keyword:
            rows = execute_query(sql + " AND title LIKE %s ORDER BY id DESC LIMIT %s",
                                 params + (f'%{keyword}%', limit))
        else:
            rows = execute_query(sql + " ORDER BY id DESC LIMIT %s", params + (limit,))

        if not rows and keyword:
            # 无标题匹配：回退为全部可见文档，让LLM如实说明"没有'技术'相关文档"
            rows = execute_query(sql + " ORDER BY id DESC LIMIT %s", base_params + (limit,))

        pseudo = []
        for i, r in enumerate(rows):
            snippet = (r.get('content') or '').strip().replace('\n', ' ')[:120]
            text = f"【文档标题】{r['title']}。{snippet}"
            pseudo.append({
                'id': r['id'],
                'doc_id': r['id'],
                'parent_id': None,
                'source': f"document_{r['id']}",
                'tenant_id': r.get('tenant_id'),
                'content': text,
                'child_content': text,
                'score': 1e9 - i,          # 高优先级排在最前
                'rerank_score': 999.0,
                'rerank_norm': 1.0,
            })
        return pseudo

    def _merge_variants(self, variant_candidates: List[List[Dict]]) -> List[Dict]:
        """
        合并多个查询变体的候选，同一块(去重键)RRF分数累加
        """
        merged: Dict[tuple, Dict] = {}

        for variants in variant_candidates:
            for item in variants:
                key = (item.get('doc_id'), item.get('parent_id'), item.get('chunk_index'))
                if key not in merged:
                    merged[key] = dict(item)
                else:
                    merged[key]['score'] = merged[key].get('score', 0) + item.get('score', 0)

        return sorted(merged.values(), key=lambda x: x['score'], reverse=True)

    def _norm_score(self, candidate: Dict) -> float:
        """
        归一化相似度分数(0~1)
        优先使用重排后的 sigmoid 分数，否则用稠密L2距离换算
        """
        if candidate.get('rerank_norm') is not None:
            return float(candidate['rerank_norm'])
        dense = candidate.get('dense_score')
        if dense is not None:
            return 1.0 / (1.0 + float(dense))
        return 0.5  # 仅稀疏召回的块使用中性值

    def _select_dynamic_topk(self, scores: List[float], requested_top_k: int) -> int:
        """
        动态TopK调度 (特性3)
        基于分数分布决定送入LLM的块数量：
        - 峰值高且骤降 -> 单一强答案 -> 用最少块
        - 均值高(多块相关) -> 用最多块
        - 全部弱相关 -> 用最少块
        - 否则 -> 基准块数
        """
        if not DYNAMIC_CONFIG.get('enabled', True) or not scores:
            return requested_top_k or DYNAMIC_CONFIG.get('base_topk', 5)

        min_topk = int(DYNAMIC_CONFIG.get('min_topk', 3))
        max_topk = int(DYNAMIC_CONFIG.get('max_topk', 8))
        base_topk = int(DYNAMIC_CONFIG.get('base_topk', 5))
        high_threshold = float(DYNAMIC_CONFIG.get('high_threshold', 0.85))
        low_threshold = float(DYNAMIC_CONFIG.get('low_threshold', 0.5))

        sorted_scores = sorted(scores, reverse=True)
        top = sorted_scores[0]
        drop = (sorted_scores[0] - sorted_scores[1]) if len(sorted_scores) > 1 else 1.0
        mean = sum(sorted_scores) / len(sorted_scores)

        if top >= high_threshold and drop >= 0.15:
            k = min_topk                       # 单一强答案
        elif mean >= high_threshold:
            k = max_topk                       # 高度相关且集中
        elif top <= low_threshold:
            k = min_topk                       # 全部弱相关
        else:
            k = base_topk

        # 钳制范围并尊重调用方上限
        k = max(min_topk, min(k, max_topk))
        if requested_top_k:
            k = min(k, requested_top_k)
        return k

    def _to_output_doc(self, candidate: Dict) -> Dict[str, Any]:
        """将候选块转换为输出文档(父窗口作为作答上下文)"""
        child_text = candidate.get('text', '')
        parent_text = _parent_map.get(candidate.get('parent_id'), child_text)

        return {
            'id': candidate.get('doc_id'),
            'doc_id': candidate.get('doc_id'),
            'parent_id': candidate.get('parent_id'),
            'source': candidate.get('source'),
            'tenant_id': candidate.get('tenant_id'),
            'content': parent_text,            # 父窗口(作答上下文)
            'child_content': child_text,       # 子块(检索原文)
            'score': candidate.get('score'),   # RRF融合分
            'rerank_score': candidate.get('rerank_score'),
            'rerank_norm': candidate.get('rerank_norm'),
        }

    def retrieve_documents(
        self,
        query: str,
        top_k: int = 5,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        检索与查询最相关的文档（完整混合检索管线）

        Args:
            query: 查询文本
            top_k: 返回的文档数量
            tenant_id: 租户过滤(admin传None可见全部)
            user_id: 查询用户ID(所有者恒可见)
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(用于查询改写时指代消解)

        Returns:
            List[Dict]: 相关文档列表
        """
        if not LANCHAIN_AVAILABLE:
            return self._mock_retrieve(query, top_k)

        docs, _ = self._hybrid_retrieve(query, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history)
        return docs

    def _mock_retrieve(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        模拟检索（当LangChain不可用时）

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            List[Dict]: 模拟的文档列表
        """
        from application.utils.db_utils import execute_query

        sql = """
            SELECT id, title, content FROM tb_document
            WHERE status = 'completed'
            LIMIT 10
        """
        docs = execute_query(sql)

        results = []
        for doc in docs[:top_k]:
            content = doc['content'] or ''
            score = 0.5 if query.lower() in content.lower() else 0.3
            results.append({
                'id': doc['id'],
                'title': doc['title'],
                'content': content[:500],
                'score': score
            })

        return results

    # ============================================================
    # 答案生成
    # ============================================================
    def generate_answer(self, question: str, context_documents: List[Dict], history: Optional[List[Dict]] = None) -> str:
        """
        使用LLM生成回答（上下文为父窗口文本）

        Args:
            question: 用户问题
            context_documents: 上下文文档列表
            history: 会话历史(供LLM理解指代与语境)

        Returns:
            str: 生成的回答
        """
        try:
            context = "\n\n".join([
                f"文档{i+1}:\n{doc.get('content', '')}"
                for i, doc in enumerate(context_documents)
            ])

            prompt = load_rag_prompt().format(
                context=context, question=question,
                history=build_dialogue_text(history)
            )
            return self._call_llm(prompt)
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return self._mock_generate_answer(question, context_documents)

    def _call_llm(self, prompt: str) -> str:
        """
        调用LLM大模型 (oMLX Qwen3.5-9B)

        Args:
            prompt: 提示词

        Returns:
            str: 模型生成的回复
        """
        try:
            response = requests.post(
                f"{LLM_CONFIG['api_base']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {LLM_CONFIG.get('api_key', 'dummy')}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': LLM_CONFIG['model_name'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': LLM_CONFIG['temperature'],
                    'max_tokens': LLM_CONFIG['max_tokens']
                },
                timeout=LLM_CONFIG['timeout']
            )
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"API error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"LLM调用失败: {str(e)}"

    def _call_llm_stream(self, prompt: str) -> Iterator[str]:
        """
        流式调用LLM(oMLX)，逐token产出文本

        Args:
            prompt: 完整提示词

        Yields:
            文本增量(token)
        """
        try:
            response = requests.post(
                f"{LLM_CONFIG['api_base']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {LLM_CONFIG.get('api_key', 'dummy')}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': LLM_CONFIG['model_name'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': LLM_CONFIG['temperature'],
                    'max_tokens': LLM_CONFIG['max_tokens'],
                    'stream': True
                },
                timeout=LLM_CONFIG['timeout'],
                stream=True
            )
            if response.status_code != 200:
                yield f"API error: {response.status_code} - {response.text}"
                return
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode('utf-8', errors='ignore').strip()
                if not line.startswith('data:'):
                    continue
                data = line[len('data:'):].strip()
                if data == '[DONE]':
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get('choices') or []
                    if choices:
                        delta = (choices[0].get('delta') or {}).get('content')
                        if delta:
                            yield delta
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"LLM调用失败: {str(e)}"

    def answer_question_stream(
        self,
        question: str,
        user_id: int,
        tenant_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        流式RAG问答入口
        事件序列: retrieving(检索中) -> thinking(检索完成,LLM生成中) -> token*(增量) -> done(结束)
        命中L1/L2全量缓存时直接输出缓存答案；命中L3时跳过检索仅重新生成。

        Args:
            question: 用户问题
            user_id: 用户ID
            tenant_id: 租户ID(admin传None)
            clearance_level: 用户密级
            acl_doc_ids: ACL授权文档ID列表
            history: 会话历史(指代消解与语境理解)
        """
        top_k = int(RAG_CONFIG['top_k'])

        # 0. 全量答案缓存(L1精确/L2语义)
        try:
            cached_full = self.cache_manager.get(question, user_id, tenant_id)
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            cached_full = None
        if cached_full and cached_full.get('answer'):
            yield {'type': 'status', 'phase': 'thinking', 'retrieved_docs': [],
                   'stats': {'cache': cached_full.get('from_cache')}, 'from_cache': True}
            yield {'type': 'token', 'delta': cached_full['answer']}
            yield {'type': 'done', 'source_documents': cached_full.get('source_documents') or [],
                   'stats': {'cache': cached_full.get('from_cache')},
                   'model_used': cached_full.get('model_used') or LLM_CONFIG['model_name']}
            return

        # 1. 检索阶段(L3上下文缓存命中则跳过，查询改写/双路召回/重排耗时较长)
        yield {'type': 'status', 'phase': 'retrieving'}
        stats: Dict[str, Any] = {}
        l3 = self.cache_manager.get_l3_context(question, user_id, tenant_id)
        if l3 is not None:
            retrieved_docs, stats = l3
            stats['cache'] = 'L3'
        else:
            retrieved_docs, stats = self._hybrid_retrieve(
                question, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history
            )
        yield {'type': 'status', 'phase': 'thinking', 'retrieved_docs': retrieved_docs, 'stats': stats}

        # 2. 生成阶段(流式输出)
        answer_parts: List[str] = []
        try:
            context = "\n\n".join([
                f"文档{i+1}:\n{doc.get('content', '')}"
                for i, doc in enumerate(retrieved_docs)
            ])
            prompt = load_rag_prompt().format(
                context=context, question=question,
                history=build_dialogue_text(history)
            )
            for delta in self._call_llm_stream(prompt):
                answer_parts.append(delta)
                yield {'type': 'token', 'delta': delta}
        except Exception as e:
            logger.error(f"Stream generate failed: {e}")
            yield {'type': 'token', 'delta': f"（生成回答失败：{e}）"}

        # 3. 结束事件
        source_doc_ids = list(dict.fromkeys([doc['id'] for doc in retrieved_docs if doc.get('id')]))
        yield {
            'type': 'done',
            'source_documents': source_doc_ids,
            'stats': stats,
            'model_used': LLM_CONFIG['model_name']
        }

        # 4. 热点问题写入各级缓存
        try:
            self.cache_manager.try_cache_hot_question(
                question, ''.join(answer_parts), source_doc_ids, LLM_CONFIG['model_name'],
                retrieved_docs=retrieved_docs, retrieval_stats=stats,
                user_id=user_id, tenant_id=tenant_id
            )
        except Exception as e:
            logger.warning(f"Cache hot question failed: {e}")

    def _mock_generate_answer(self, question: str, context_documents: List[Dict]) -> str:
        """
        模拟回答生成

        Args:
            question: 用户问题
            context_documents: 上下文文档

        Returns:
            str: 模拟回答
        """
        if not context_documents:
            return "抱歉，知识库中暂时没有找到相关信息。"

        context_text = "\n".join([doc.get('content', '')[:300] for doc in context_documents])

        return f"""根据检索到的相关文档，我为您找到以下信息：

{context_text[:500]}...

如果您需要了解更多详情，请提出更具体的问题。"""

    def answer_question(
        self,
        question: str,
        user_id: int,
        tenant_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        RAG问答的入口方法
        完整流程：缓存检查 -> 查询改写 -> 混合检索 -> 重排 -> 动态TopK -> 父窗口作答

        Args:
            question: 用户问题
            user_id: 用户ID
            tenant_id: 所属租户ID
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(指代消解与语境理解)

        Returns:
            Dict: 包含回答、源文档、token消耗等
        """
        top_k = int(RAG_CONFIG['top_k'])

        # 0. 缓存检查(L1精确/L2语义返回完整答案；L3返回检索结果仅省去检索)
        try:
            cached = self.cache_manager.get(question, user_id, tenant_id)
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            cached = None

        if cached and cached.get('answer'):
            answer = cached['answer']
            source_doc_ids = cached.get('source_documents') or []
            return {
                'answer': answer,
                'source_documents': source_doc_ids,
                'retrieved_docs': [],
                'model_used': cached.get('model_used') or LLM_CONFIG['model_name'],
                'token_count': len(question) + len(answer),
                'topk_used': 0,
                'retrieval_stats': {'cache': cached.get('from_cache')},
                'from_cache': cached.get('from_cache')
            }

        # 1. 混合检索（L3命中则复用检索结果）
        l3 = self.cache_manager.get_l3_context(question, user_id, tenant_id)
        if l3 is not None:
            retrieved_docs, stats = l3
            stats['cache'] = 'L3'
        else:
            retrieved_docs, stats = self._hybrid_retrieve(
                question, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history
            )

        # 2. 生成回答
        answer = self.generate_answer(question, retrieved_docs, history)

        # 3. 提取源文档ID(修复历史恒为空的问题)
        source_doc_ids = list(dict.fromkeys([doc['id'] for doc in retrieved_docs if doc.get('id')]))

        # 4. 热点问题写入各级缓存
        try:
            self.cache_manager.try_cache_hot_question(
                question, answer, source_doc_ids, LLM_CONFIG['model_name'],
                retrieved_docs=retrieved_docs, retrieval_stats=stats,
                user_id=user_id, tenant_id=tenant_id
            )
        except Exception as e:
            logger.warning(f"Cache hot question failed: {e}")

        return {
            'answer': answer,
            'source_documents': source_doc_ids,
            'retrieved_docs': retrieved_docs,
            'model_used': LLM_CONFIG['model_name'],
            'token_count': len(question) + len(answer),  # 粗略估算
            'topk_used': stats.get('topk_used'),
            'retrieval_stats': stats
        }

    # ============================================================
    # 向量库重建
    # ============================================================
    def reload_all_documents(self, tenant_id: Optional[int] = None) -> Dict[str, Any]:
        """
        重新加载所有已完成的文档到向量库（重建Chroma + BM25 + 父窗口映射）

        Args:
            tenant_id: 仅重建指定租户(为空则全部)

        Returns:
            Dict: 重载结果统计
        """
        if not LANCHAIN_AVAILABLE or self.embeddings is None:
            return {'success': False, 'message': 'LangChain not available'}

        from application.utils.db_utils import execute_query

        # 获取文档列表（含权限字段，写入块元数据）
        if tenant_id is not None:
            sql = ("SELECT id, file_path, title, tenant_id, doc_level, min_level, upload_by "
                   "FROM tb_document WHERE status = 'completed' AND tenant_id = %s")
            documents = execute_query(sql, (tenant_id,))
        else:
            sql = ("SELECT id, file_path, title, tenant_id, doc_level, min_level, upload_by "
                   "FROM tb_document WHERE status = 'completed'")
            documents = execute_query(sql)

        success_count = 0
        fail_count = 0

        try:
            # 清空旧向量库（原地 reset，避免删除目录导致 Chroma 客户端连接失效）
            if self.vectorstore is not None:
                try:
                    self.vectorstore.reset_collection()
                    logger.info("Chroma collection reset")
                except Exception as e:
                    logger.error(f"Failed to reset collection: {e}")
                    self.vectorstore = None
                    persist_dir = CHROMA_CONFIG['persist_directory']
                    if os.path.exists(persist_dir):
                        shutil.rmtree(persist_dir)
                    os.makedirs(persist_dir, exist_ok=True)

            # 清空BM25与父窗口映射
            self.bm25.clear()
            global _parent_map
            with _parent_lock:
                _parent_map = {}
            _save_parent_map()

            for doc in documents:
                if os.path.exists(doc['file_path']):
                    if self.add_document_to_vectorstore(
                        doc['file_path'],
                        doc_id=doc['id'],
                        tenant_id=doc['tenant_id'],
                        doc_level=doc.get('doc_level') or 'public',
                        min_level=doc.get('min_level') or 1,
                        owner_id=doc.get('upload_by')
                    ):
                        success_count += 1
                    else:
                        fail_count += 1
                else:
                    fail_count += 1

            return {
                'success': True,
                'total': len(documents),
                'success_count': success_count,
                'fail_count': fail_count,
                'tenant_id': tenant_id
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
        finally:
            self.cache_manager.clear_all()

    # ============================================================
    # 模型热插拔（配合 /api/model 管理接口：DB配置优先于YAML）
    # ============================================================
    def apply_active_models(self):
        """读取DB中启用的模型配置，原地覆盖运行时字典（LLM立即生效；嵌入仅在维度兼容时热切）"""
        from application.utils.db_utils import execute_query
        try:
            rows = execute_query(
                "SELECT model_type, api_base, api_key, model_name, pending_rebuild "
                "FROM tb_model_config WHERE is_active = 1"
            )
        except Exception as e:
            logger.warning(f"apply_active_models: 读取模型配置失败(回退YAML): {e}")
            return {'llm': False, 'embedding': False}

        applied = {'llm': False, 'embedding': False}
        for r in rows:
            if r['model_type'] == 'llm':
                LLM_CONFIG['api_base'] = r['api_base']
                LLM_CONFIG['api_key'] = r.get('api_key') or ''
                LLM_CONFIG['model_name'] = r['model_name']
                applied['llm'] = True
                logger.info(f"LLM 已切换为DB配置: {r['model_name']} @ {r['api_base']}")
            elif r['model_type'] == 'embedding':
                EMBEDDING_CONFIG['api_base'] = r['api_base']
                EMBEDDING_CONFIG['api_key'] = r.get('api_key') or ''
                EMBEDDING_CONFIG['model_name'] = r['model_name']
                self._initialize_embeddings()
                self._initialize_vectorstore()
                applied['embedding'] = True
                logger.info(f"Embedding 已切换为DB配置: {r['model_name']} @ {r['api_base']}")
        return applied

    def collection_dim(self) -> Optional[int]:
        """当前Chroma集合的向量维度（空库返回None）"""
        if self.vectorstore is None:
            return None
        try:
            res = self.vectorstore._collection.get(limit=1, include=['embeddings'])
            embs = res.get('embeddings')   # chromadb 1.x 返回 numpy.ndarray
            if embs is None or len(embs) == 0:
                return None
            return int(len(embs[0]))
        except Exception:
            return None

    def probe_embedding_dim(self, api_base: str, api_key: str, model_name: str) -> int:
        """探测指定嵌入配置的输出维度（临时实例，不影响运行时）"""
        tmp = OMLXEmbeddings(api_base=api_base, api_key=api_key or '', model_name=model_name)
        vec = tmp.embed_documents(['维度探测'])
        return len(vec[0])

    def hot_swap_llm(self, cfg: dict):
        """切换LLM并清空答案相关缓存（旧模型的缓存答案不再适用）"""
        LLM_CONFIG['api_base'] = cfg['api_base']
        LLM_CONFIG['api_key'] = cfg.get('api_key') or ''
        LLM_CONFIG['model_name'] = cfg['model_name']
        try:
            self.cache_manager.clear_all()
        except Exception:
            pass
        logger.info(f"LLM 热切换完成: {cfg['model_name']} @ {cfg['api_base']}")

    def hot_swap_embedding(self, cfg: dict) -> dict:
        """
        切换嵌入模型。维度不兼容时不热切，要求先重建向量库。
        Returns: {swapped, rebuild_required, old_dim, new_dim}
        """
        new_dim = self.probe_embedding_dim(cfg['api_base'], cfg.get('api_key'), cfg['model_name'])
        old_dim = self.collection_dim()

        if old_dim is not None and old_dim != new_dim:
            logger.warning(f"嵌入维度不兼容({old_dim}→{new_dim})，需重建向量库后生效")
            return {'swapped': False, 'rebuild_required': True,
                    'old_dim': old_dim, 'new_dim': new_dim}

        EMBEDDING_CONFIG['api_base'] = cfg['api_base']
        EMBEDDING_CONFIG['api_key'] = cfg.get('api_key') or ''
        EMBEDDING_CONFIG['model_name'] = cfg['model_name']
        self._initialize_embeddings()
        self._initialize_vectorstore()
        try:
            self.cache_manager.clear_all()
        except Exception:
            pass
        return {'swapped': True, 'rebuild_required': False,
                'old_dim': old_dim, 'new_dim': new_dim}
