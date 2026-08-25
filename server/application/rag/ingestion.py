# -*- coding: utf-8 -*-
"""P1重构：自 services/rag_service.py 机械搬移（行为等价，Mixin承载）"""
import json
import os
import re
import time
import shutil
import logging
from typing import List, Dict, Any, Iterator, Optional

import requests

from utils.logger_handler import logger
from utils.config_handler import config
from application.utils.db_utils import execute_query, execute_update, execute_insert
from application.rag import state
from application.rag.state import (_parent_map, _parent_lock, _save_parent_map, DATA_DIR,
    LANCHAIN_AVAILABLE, Chroma, TextLoader, PyPDFLoader, RecursiveCharacterTextSplitter)

RAG_CONFIG = config.get_section('rag')
HYBRID_CONFIG = RAG_CONFIG.get('hybrid', {})
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
DYNAMIC_CONFIG = RAG_CONFIG.get('dynamic_topk', {})
ENUM_CONFIG = RAG_CONFIG.get('enumeration', {})


from application.services.document_parser import parse_document
from application.services.chunking import build_parent_child_chunks, build_parent_child_chunks_from_elements


def _write_parse_stats(doc_id: int, file_path: str, stats: dict) -> None:
    """追加解析统计到 server/data/parse_stats.jsonl（便于事后排查解析质量）"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        row = {'doc_id': doc_id, 'file': os.path.basename(file_path), 'time': __import__('datetime').datetime.now().isoformat(timespec='seconds'), **stats}
        with open(os.path.join(DATA_DIR, 'parse_stats.jsonl'), 'a', encoding='utf-8') as f:
            f.write(__import__('json').dumps(row, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.warning(f"write parse stats failed: {e}")




class IngestionMixin:
    """文档解析入库：加载→分块→向量化→BM25→父窗口映射"""
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
            with _parent_lock:
                _parent_map.clear()
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
