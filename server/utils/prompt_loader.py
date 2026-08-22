# -*- coding: utf-8 -*-
"""
提示词加载器模块
从外部文件加载系统提示词
"""

import os
from typing import Dict, List, Optional


def build_dialogue_text(history: Optional[List[Dict]], max_turns: int = 3) -> str:
    """
    将会话历史转为提示词中的对话文本块

    Args:
        history: [{'question': str, 'answer': str}, ...]（按时间正序）
        max_turns: 最多保留最近几轮

    Returns:
        str: "用户：.../助手：..." 多行文本，无历史时返回"无"
    """
    if not history:
        return '无'
    lines = []
    for turn in history[-max_turns:]:
        q = (turn.get('question') or '').strip()
        a = (turn.get('answer') or '').strip()
        if q:
            lines.append(f"用户：{q[:200]}")
        if a:
            lines.append(f"助手：{a[:300]}")
    return '\n'.join(lines) if lines else '无'


def load_prompt_file(file_path: str) -> str:
    """
    加载单个提示词文件

    Args:
        file_path: 提示词文件路径

    Returns:
        str: 文件内容，失败返回空字符串
    """
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    except Exception as e:
        print(f"加载提示词文件失败 {file_path}: {e}")
        return ""


def load_system_prompts() -> str:
    """
    加载系统主提示词

    Returns:
        str: 系统提示词内容
    """
    prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(prompts_dir, 'prompts', 'main_prompt.txt')
    return load_prompt_file(prompt_path)


def load_query_rewrite_prompt() -> str:
    """
    加载查询改写提示词

    Returns:
        str: 查询改写提示词内容
    """
    prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(prompts_dir, 'prompts', 'query_rewrite_prompt.txt')
    content = load_prompt_file(prompt_path)
    if not content:
        content = """你是一个RAG检索查询优化助手。请结合对话历史，将用户最新问题改写为 {num} 个更利于检索的查询变体，并将代词替换为具体对象。

对话历史:
{history}

用户最新问题: {question}

请只输出JSON数组字符串，例如：["改写一", "改写二"]"""
    return content


def load_rag_prompt() -> str:
    """
    加载RAG问答提示词

    Returns:
        str: RAG提示词内容
    """
    prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(prompts_dir, 'prompts', 'rag_prompt.txt')
    content = load_prompt_file(prompt_path)
    # 如果文件不存在，返回默认提示词
    if not content:
        content = """基于以下文档内容回答用户问题。如果文档中没有相关信息，请说明不知道。

对话历史:
{history}

文档内容:
{context}

用户问题: {question}

请根据文档内容给出回答："""
    return content