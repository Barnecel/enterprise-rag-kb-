# -*- coding: utf-8 -*-
"""
LangChain RAG服务示例代码
演示如何通过LangChain集成oMLX的Qwen3.5-9B-MLX-4bit大模型
和Qllama的Qwen3-Embedding-8B-4bit-DWQ嵌入模型
"""

# =============================================
# LangChain RAG 完整示例
# =============================================

# 安装依赖:
# pip install langchain langchain-community langchain-huggingface
# pip install chromadb sentence-transformers
# pip install torch (CPU版本或根据需要安装CUDA版本)

"""
完整RAG流程示例代码：

from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# 1. 初始化嵌入模型 (Qwen3-Embedding-8B-4bit-DWQ)
embeddings = HuggingFaceEmbeddings(
    model_name="Qwen3-Embedding-8B-4bit-DWQ",
    model_kwargs={'device': 'cpu'}
)

# 2. 加载文档
loader = TextLoader("document.txt", encoding="utf-8")
documents = loader.load()

# 3. 文档分割
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)
chunks = text_splitter.split_documents(documents)

# 4. 存储到Chroma向量库
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_data"
)

# 5. 检索相关文档
query = "用户问题"
results = vectorstore.similarity_search(query, k=5)

# 6. 构建提示词
context = "\n".join([doc.page_content for doc in results])
prompt = f"上下文: {context}\n\n问题: {query}\n\n请根据上下文回答问题"

# 7. 调用oMLX的Qwen3.5-9B-MLX-4bit (根据实际API配置)
# response = omlx_model.generate(prompt)

print("RAG流程完成")
"""