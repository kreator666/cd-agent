# 知识库文档上传 → RAG 入库流程分析

> 分析日期：2026-05-27
> 分析范围：前端 knowledge.html → 后端 API → RAG 向量库全链路

---

## 一、前端上传（frontend/knowledge.html）

### 代码位置
`frontend/knowledge.html` 第 152~169 行

### 流程
```javascript
async function uploadDocuments() {
    const formData = new FormData();
    for (const file of input.files) { 
        formData.append('files', file); 
    }
    await fetch('/documents/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
    });
}
```

### 关键说明
- 前端只把文件塞进了 `FormData`，**没有传 `kind` 和 `style`**（虽然后端 API 已支持这两个字段）
- 也就是说，目前从前端上传的文档默认不带"种类/风格"分类标签
- 支持的文件类型由后端决定，前端无限制

---

## 二、后端 API 接收（src/comedy_agent/api/server.py）

### 代码位置
`src/comedy_agent/api/server.py` 第 950~1039 行

### 流程

1. **保存原始文件到磁盘**
   ```
   data/uploads/{user_id}/单立人sketch手册.pdf
   ```

2. **写 SQLite 记录**（`userdocument` 表）
   - `status = "pending"`（处理中）
   - `filename`：原始文件名
   - `doc_id`：UUID
   - `user_id`：当前用户
   - `chunk_count = 0`
   - `error_msg = null`

3. **调用知识库导入器**
   ```python
   ingestor = KnowledgeIngestor(chunk_strategy="paragraph")
   user_vector_store = VectorStore(
       collection_name=f"user_knowledge_{user_id}",
       persist_path=str(settings.vector_db_path),
   )
   user_retriever = ComedyRetriever(vector_store=user_vector_store)
   ingestor.retriever = user_retriever
   result = ingestor.ingest_file(save_path)
   ```
   注意：`kind` 和 `style` 参数目前为 `None`（前端未传）

4. **更新状态**
   - `status = "ingested"`（入库成功）或 `"failed"`（失败）
   - `chunk_count = result.get("chunks", 0)`
   - 若失败，记录 `error_msg`

---

## 三、文档解析（src/comedy_agent/rag/document_loader.py）

### 代码位置
`src/comedy_agent/rag/document_loader.py`

### 解析策略（按扩展名）

| 格式 | 扩展名 | 解析方式 |
|------|--------|---------|
| 纯文本 | `.txt` `.md` `.json` `.csv` `.rst` | 直接读取文本内容 |
| 字幕 | `.srt` `.ass` `.vtt` `.ssa` | 字幕解析器，**保留时间码元数据** |
| 富文档 | `.pdf` `.docx` `.doc` `.html` `.htm` | `unstructured` 解析（失败时降级到纯文本） |

### 输出
解析后得到 `list[Document]`，每个 Document 包含：
- `page_content`：文本内容
- `metadata`：文件路径（`source`）等

---

## 四、文本分块（src/comedy_agent/rag/chunker.py）

### 代码位置
`src/comedy_agent/rag/chunker.py`

### 默认配置
```python
chunk_strategy = "paragraph"   # 按段落分块
chunk_size = 800               # 每块约 800 字符
chunk_overlap = 100            # 相邻块重叠 100 字符
```

### 可选策略

| 策略 | 适用场景 |
|------|---------|
| `fixed` | 通用固定大小分块 |
| `paragraph` | 理论书籍、文章（默认） |
| `scene` | 剧本（按场景分隔符分块） |
| `dialogue` | 相声/小品（按角色对话分块） |
| `subtitle` | 视频字幕（按时间窗口合并） |

### 分块后处理
- 每个 chunk 是一个新的 `Document`
- metadata 继承原始文档
- 若上传时指定了 `kind`/`style`，会附加到每个 chunk 的 metadata：
  ```python
  chunk.metadata["kind"] = kind      # 如 "sketch"
  chunk.metadata["style"] = style    # 如 "traditional"
  ```

---

## 五、向量入库（src/comedy_agent/rag/retriever.py + vector_store.py）

### 代码位置
- `src/comedy_agent/rag/retriever.py` 第 116~131 行（`ingest` 方法）
- `src/comedy_agent/rag/vector_store.py` 第 86~117 行（`add_documents` 方法）

### 入库流程

**1. 向量库入库**
```python
self.vector_store.add_documents(chunks)
```

内部子流程：
1. 调用 HuggingFace `all-MiniLM-L6-v2`（384 维）生成 Embedding
2. 写入 **ChromaDB** 集合：`user_knowledge_{user_id}`
3. 每个 chunk 的 metadata 包含：
   - `source`: 原始文件路径
   - `doc_id`: chunk 的唯一 ID（UUID）
   - `kind`: 喜剧种类（若上传时指定）
   - `style`: 风格（若上传时指定）

**2. 更新 BM25 索引**
```python
self._build_bm25_index()   # 构建关键词倒排索引
```
- 同时更新 ComedyRetriever 的 BM25 索引
- 支持后续"向量检索 + 关键词检索"混合召回

---

## 六、最终存储位置

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 原始文件 | `data/uploads/{user_id}/文件名.pdf` | 磁盘文件，上传时保存 |
| 文档记录 | SQLite `data/memory.db` → `userdocument` 表 | 元数据、状态、错误信息 |
| 向量数据 | ChromaDB `chroma_data/` → `user_knowledge_{user_id}` 集合 | 分块后的文本 + Embedding |
| Embedding 模型 | HuggingFace `all-MiniLM-L6-v2` | 本地运行，384 维，无需 API Key |
| BM25 索引 | 内存中（ComedyRetriever._bm25） | 服务重启后重建 |

---

## 七、删除时的同步清理

### 代码位置
`src/comedy_agent/api/server.py` 第 1053~1097 行

### 流程
1. **从 ChromaDB 清理向量**
   ```python
   filter_conditions = {"source": {"$contains": doc.filename}}
   matched = user_vector_store.get_by_filter(filter_conditions)
   user_vector_store.delete(ids_to_delete)
   ```
   按 `source` 字段（文件路径）过滤，删除该文件的所有 chunks

2. **删除本地文件**
   ```python
   file_path = upload_dir / doc.filename
   file_path.unlink()
   ```

3. **删除 SQLite 记录**
   ```python
   state.memory.delete_document(user_id, doc_id)
   ```

---

## 八、当前前端缺少的功能

### 1. kind/style 选择器

**现状**：后端 API 已支持上传时带 `kind` 和 `style`：
```python
@app.post("/documents/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    kind: str | None = Form(default=None),      # 喜剧种类
    style: str | None = Form(default=None),     # 风格
    ...
)
```

**前端缺失**：`knowledge.html` 的 `FormData` 只 append 了 `files`，没有 `kind`/`style`。

**影响**：上传的文档默认不带分类标签，所有 Skill 都能检索到，无法实现"小品 Skill 只检索小品手册"的精准过滤。

### 2. 上传进度/结果反馈

**现状**：上传后只弹一个简单 `alert`，没有展示：
- 解析了多少 chunk
- Embedding 生成耗时
- 入库成功/失败的详细原因

### 3. 分块策略选择

**现状**：后端固定使用 `paragraph` 策略，前端无选择入口。

**建议**：上传 PDF/剧本时，允许用户选择分块策略（paragraph / scene / dialogue）。

---

## 九、流程图

```
用户选择文件
    │
    ▼
前端 FormData → POST /documents/upload
    │
    ▼
后端 API
    ├── 保存文件 → data/uploads/{user_id}/
    ├── 写 SQLite → userdocument (status=pending)
    └── 调用 KnowledgeIngestor
            │
            ▼
        DocumentLoader.load(path)
            ├── .txt/.md → 直接读取
            ├── .srt/.ass/.vtt → 字幕解析（保留时间码）
            └── .pdf/.docx → unstructured 解析
            │
            ▼
        DocumentChunker.auto_split(strategy="paragraph")
            ├── chunk_size=800
            ├── overlap=100
            └── 附加 kind/style metadata
            │
            ▼
        ComedyRetriever.ingest(chunks)
            ├── VectorStore.add_documents()
            │       └── HuggingFace Embedding → ChromaDB
            │           collection: user_knowledge_{user_id}
            └── 更新 BM25 索引
            │
            ▼
        更新 SQLite → status=ingested, chunk_count=N
```

---

## 十、关键配置项

| 配置 | 位置 | 默认值 |
|------|------|--------|
| 分块策略 | `KnowledgeIngestor.__init__` | `"paragraph"` |
| 分块大小 | `KnowledgeIngestor.__init__` | `800` |
| 重叠长度 | `KnowledgeIngestor.__init__` | `100` |
| Embedding 模型 | `.env` → `EMBEDDING_MODEL` | `"hf-local"` |
| 向量库路径 | `.env` → `VECTOR_DB_PATH` | `"./chroma_data"` |
| 个人知识库集合名 | `VectorStore.__init__` | `"user_knowledge_{user_id}"` |
