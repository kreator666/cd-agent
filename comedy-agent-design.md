# 喜剧行业垂直 Agent —— 设计方案与实现问答

## 一、方案选择：方案二（一体化 Agent 框架）

**技术栈**：LangChain / LangGraph + 多模型协作 + RAG 知识库 + 记忆系统

**适用场景**：快速启动、迭代验证想法、社区支持好

**当前状态**：第一、二阶段已实现并验证通过，第三~五阶段已预留接口。

---

## 二、核心问题解答

### Q1：方案2能支持 Skill 么？

**能。** 在 LangChain 框架中，Skill 对应 **Tool（工具）** 的概念。每个喜剧子类型或辅助能力都可以封装为一个独立的 Tool。

**实现方式**：
- 继承 `BaseTool`，定义 `args_schema`（输入参数）
- 内部封装专家级 Prompt 模板
- Agent 初始化时注册所有 Skill，运行时自动路由

**进阶**：可设计为动态加载（插件化），从本地 `skills/` 目录读取 `SKILL.md` 和 `prompt.txt` 自动注册。

> ✅ **已实现**：6 个内置 Skill（脱口秀、相声、小品、情景喜剧、笑点分析、剧本评估）+ 插件化 Skill 加载机制（声明式 + 代码式）。

---

### Q2：喜剧行业知识库如何实现 RAG？

**数据来源**：
| 类型 | 示例 |
|------|------|
| 理论书籍 | 《喜剧的艺术》、郭德纲相声理论 |
| 经典剧本 | 春晚小品剧本、脱口秀专场逐字稿 |
| 视频字幕 | 喜剧综艺、专场演出 |
| 行业知识 | 喜剧结构理论、笑点公式 |
| 用户私有 | 用户创作、团队梗库 |

**技术架构**：
1. **文档加载**：PDF/Word/网页 → Unstructured / DocumentLoader
2. **智能分块**：按"场景"或"笑点单元"分块，保留上下文元数据（类型、角色、场景）
3. **向量化存储**：text-embedding-3-large / BGE-M3 + ChromaDB（本地）/ Milvus（大规模）
4. **混合检索**：向量检索（语义相似）+ BM25（关键词检索）+ Cross-Encoder 重排序
5. **上下文注入**：检索结果 → System Prompt / User Context → LLM 生成

**喜剧行业特殊优化**：
- 结构感知分块（按角色对话分块）
- 多向量表示（内容向量 + 结构向量 + 风格向量）
- 高评分用户剧本自动增量入库

> ⏳ **当前状态**：`ComedyRetriever` 接口已预留（`src/comedy_agent/rag/retriever.py`），将在第三阶段实现完整 RAG 流水线。

---

### Q3：能快速切换模型么？

**可以。** LangChain 提供统一的 Model I/O 抽象。

**实现方式**：
- 建立 **ModelFactory**，统一封装 OpenAI、Anthropic、Ollama、通义千问、Moonshot 等
- 按任务类型配置不同模型（创意/分析/快速响应）
- 支持运行时动态切换和故障自动 Fallback

**推荐配置**：
| 任务 | 推荐模型 |
|------|---------|
| 剧本创作 | Claude 3.5 Sonnet / GPT-4o |
| RAG/分析 | GPT-4o / Qwen2.5 |
| 本地备用 | Qwen2.5-72B |

> ✅ **已实现**：ModelFactory 支持 5 家提供商、13+ 模型，支持按 `creative` / `analytical` / `fast` 任务类型自动选择模型，支持 RunnableWithFallbacks 自动降级。

---

### Q4：记忆库和 RAG 是什么关系？

| 维度 | 记忆库 (Memory) | RAG 知识库 (Knowledge) |
|------|----------------|----------------------|
| 存储内容 | "用户是谁、偏好什么、上次聊了什么" | "喜剧理论、经典案例、行业知识" |
| 时间范围 | 短期（会话级）到中期（用户级） | 长期（永久存储） |
| 更新频率 | 每次对话后更新 | 定期批量更新/人工维护 |
| 检索方式 | 按用户ID直接读取 | 按语义相似度检索 |
| 典型数据 | "喜欢黑色幽默、讨厌谐音梗" | "相声的三番四抖技巧定义" |

**一句话总结**：记忆库存"**关于用户的事**"，RAG 库存"**关于喜剧的事**"。两者互补，共同构成 Agent 的完整上下文。

> ⏳ **当前状态**：`MemoryStore` 接口已预留（`src/comedy_agent/memory/store.py`），将在第四阶段实现完整记忆存取与融合机制。

---

## 三、技术架构概览（方案二）

```
┌─────────────────────────────────────────────────────────┐
│                  喜剧 Agent 主控 (Orchestrator)            │
│                   LangGraph Agent                        │
├─────────────────────────────────────────────────────────┤
│  Skill 层      │  模型层        │  数据层                  │
│  ├─ 脱口秀 ✅   │  ├─ 创意模型 ✅ │  ├─ RAG 知识库 ⏳       │
│  ├─ 相声 ✅     │  ├─ 分析模型 ✅ │  ├─ 记忆库 ⏳           │
│  ├─ 小品 ✅     │  ├─ 快速模型 ✅ │  └─ 向量数据库 ⏳       │
│  ├─ 情景喜剧 ✅ │  └─ 本地模型 ✅ │                         │
│  ├─ 笑点分析 ✅ │                │                         │
│  ├─ 剧本评估 ✅ │                │                         │
│  └─ 插件 Skill ✅│               │                         │
└─────────────────────────────────────────────────────────┘

图例：✅ 已实现  │  ⏳ 预留接口/待实现
```

### 已实现的模型层能力

- **统一封装**：`ModelFactory` 支持 OpenAI、Anthropic、Ollama、通义千问、Moonshot
- **任务分层**：`creative` → 创意模型，`analytical` → 分析模型，`fast` → 快速模型
- **自动 Fallback**：主模型异常时自动切换到备用模型链（`RunnableWithFallbacks`）
- **Embedding**：已注册 `text-embedding-3-large` / `text-embedding-3-small`

### 已实现的 Skill 层能力

- **内置 Skill**：6 个喜剧创作与分析 Skill，覆盖脱口秀、相声、小品、情景喜剧、笑点分析、剧本评估
- **插件化加载**：扫描 `skills/` 目录，支持：
  - 声明式 Skill：`SKILL.md` + `prompt.txt` → 自动生成 Tool
  - 代码式 Skill：`SKILL.md` + `prompt.txt` + `skill.py` → 自定义实现
- **Prompt 工程化**：`PromptManager` 支持注册、版本管理、A/B 测试、Jinja2 渲染

---

## 四、执行工作流（Agent 协作规范）

### 任务执行 & Git 提交流程

**每执行一个任务，严格遵循以下步骤：**

```
1. 代码变更  →  git add -A
2. git commit -m "task X.Y: <任务描述>
   - 变更点 1
   - 变更点 2"
3. git push origin feature
4. 记录 → vibe-log/2026-05-07-task-X.Y.md
   - 阶段、任务编号、任务名称
   - 完成内容摘要
   - Commit ID、Message、Branch、Remote
   - 备注（测试通过率、关键 API 等）
5. 等待用户下一条指令
```

**为什么这样设计？**
- 每个任务独立 commit，确保代码可追溯、可回滚
- push 到 feature 分支保持主干干净，支持 PR 评审
- vibe-log 作为执行记忆，便于复盘与 Agent 上下文恢复
- 等待指令避免擅自推进，确保人对齐

### 当前已实现的任务清单

| 阶段 | 任务 | 状态 |
|------|------|------|
| 第一阶段 | 1.1 项目脚手架搭建 | ✅ 已完成 |
| 第一阶段 | 1.2 ModelFactory 实现 | ✅ 已完成 |
| 第一阶段 | 1.3 基础 Agent 主控 | ✅ 已完成 |
| 第一阶段 | 1.4 首个 MVP Skill（脱口秀） | ✅ 已完成 |
| 第一阶段 | 1.5 基础交互接口（CLI + HTTP） | ✅ 已完成 |
| 第二阶段 | 2.1 全量 Skill 开发 | ✅ 已完成 |
| 第二阶段 | 2.2 Skill 插件化机制 | ✅ 已完成 |
| 第二阶段 | 2.3 模型分层配置 | ✅ 已完成 |
| 第二阶段 | 2.4 模型自动 Fallback | ✅ 已完成 |
| 第二阶段 | 2.5 Prompt 模板工程化 | ✅ 已完成 |
| 第三阶段 | 3.1~3.7 RAG 知识库建设 | ⏳ 未开始 |
| 第四阶段 | 4.1~4.5 记忆系统与用户层 | ⏳ 未开始 |
| 第五阶段 | 5.1~5.5 工程化与优化 | ⏳ 未开始 |

---

## 五、测试与质量

- **测试覆盖率**：78 个单元测试全部通过（pytest）
- **测试模块**：
  - `test_models_factory.py` — ModelFactory 注册、获取、Fallback
  - `test_skills_standup.py` — Skill 元数据、参数、执行
  - `test_skills_loader.py` — 插件 Skill 解析与加载
  - `test_agent_orchestrator.py` — Agent 构建、Skill 注册、对话
  - `test_api_cli.py` / `test_api_server.py` — CLI 与 HTTP API
  - `test_prompt_manager.py` — Prompt 注册、渲染、A/B 测试
