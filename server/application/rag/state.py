# -*- coding: utf-8 -*-
"""跨模块共享状态：BM25单例、父窗口映射及其持久化、LangChain可用性"""
import os
import pickle
import threading
from typing import Dict

from utils.logger_handler import logger
from application.services.bm25_retriever import BM25Retriever

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_community.document_loaders import TextLoader, PyPDFLoader
    LANCHAIN_AVAILABLE = True
except ImportError:
    LANCHAIN_AVAILABLE = False
    Chroma = None
    TextLoader = PyPDFLoader = None
    RecursiveCharacterTextSplitter = None
    logger.warning("LangChain not installed. RAG functionality will be limited.")

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(SERVER_DIR, 'data')
PARENT_MAP_FILE = os.path.join(DATA_DIR, 'parent_map.pkl')

_bm25 = BM25Retriever()
_parent_map: Dict[str, str] = {}
_parent_lock = threading.Lock()

def _load_parent_map():
    """从磁盘加载父窗口映射"""
    global _parent_map
    if os.path.exists(PARENT_MAP_FILE):
        try:
            with open(PARENT_MAP_FILE, 'rb') as f:
                _parent_map.clear()
                _parent_map.update(pickle.load(f) or {})
            logger.info(f"Parent map loaded from disk: {len(_parent_map)} entries")
        except Exception as e:
            logger.error(f"Failed to load parent map: {e}")
            _parent_map.clear()


def _save_parent_map():
    """持久化父窗口映射"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PARENT_MAP_FILE, 'wb') as f:
            pickle.dump(_parent_map, f)
    except Exception as e:
        logger.error(f"Failed to save parent map: {e}")


_load_parent_map()
