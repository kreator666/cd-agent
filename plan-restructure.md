# 喜剧AI Agent 前端 & 交互层重构计划

> 基于 `data/need-data/原型.html` 重新规划系统功能。
> **核心约束**：不改动模型交互层（`ModelFactory`、`AgentOrchestrator` 核心逻辑）、不改动 Skill 体系、不改动用户与模型的对话流程（`/chat` 端点）。仅在前端与 API 交互层做改动。

---

## 一、现状 vs 原型差距分析

| 原型模块 | 当前系统 | 差距 |
|---------|---------|------|
| 登录/注册 + Token 赠送 | 有基础 JWT 登录注册 | 缺 Token 账户体系 |
| 创作工坊（三栏布局） | `index.html` 单栏聊天 | 缺项目、加点盐、IP 风格、收益面板 |
| 🧂 加点盐（文本润色） | 无 | 需新增功能，但底层复用 `/chat` |
| 🎤 喜剧创作（IP 风格模型） | 有 Skill 直调接口 | 缺 IP 风格数据层与前端选择器 |
| 生成结果（投稿/导出/点赞） | 仅保存作品 | 缺投稿、收益、导出功能 |
| 🤖 虚拟演员 Agent | 无 | 前端包装，底层复用 `/chat` |
| 🔥 热门 IP / 统计面板 | 无 | 需数据聚合接口 |
| 🎤 演员工作台 | 无 | 需新增页面与数据模型 |
| ⚙️ 管理控制台 | `skills.html` 仅 Skill 列表 | 缺审核、IP 管理、平台概览、敏感词 |

---

## 二、总体策略："包装而非侵入"

由于核心 AI 链路不能动，所有新功能都在**现有链路之上做包装**：

1. **加点盐** → 前端包装为独立卡片，调用 `/chat` 并附加 `system_hint: "加点盐"`，模型输出风格化文本。
2. **IP 风格模型** → 数据层新增 `ip_styles` 表记录风格元数据；前端选择 IP 后，将风格描述注入 `chat_history` 作为 system hint，不改变 Skill 内部逻辑。
3. **虚拟演员 Agent** → 前端选择演员后，调用 `/chat` 并在 prompt 前注入角色设定（如 `"你是鸟鸟，社恐式幽默..."`）。
4. **投稿/收益** → 纯业务数据层，与模型层无关。
5. **Token 消耗** → API 层在返回前按调用类型扣减用户余额，失败不扣费。

---

## 三、数据层重构（SQLite Schema 扩展）

在 `memory/schema.py` 中**新增**以下表，现有表完全不改动：

### 3.1 用户 Token 账户表
```python
class UserTokenAccount(Base):
    __tablename__ = "user_token_accounts"
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=5000)  # 新用户赠 5000
    total_consumed: Mapped[int] = mapped_column(Integer, default=0)
    total_recharged: Mapped[int] = mapped_column(Integer, default=0)
```

### 3.2 项目表（取代松散的作品列表）
```python
class UserProject(Base):
    __tablename__ = "user_projects"
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16])
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.user_id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256))
    project_type: Mapped[str] = mapped_column(String(32), nullable=True)  # standup / sketch / salt / mixed
    created_at / updated_at
```
将现有 `UserScript` 通过 `project_id` 外键关联到项目（新增可空列，兼容旧数据）。

### 3.3 加点盐历史表
```python
class SaltHistory(Base):
    __tablename__ = "salt_history"
    salt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey(...), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("user_projects.project_id"), nullable=True)
    original_text: Mapped[str] = mapped_column(Text)
    polished_text: Mapped[str] = mapped_column(Text)
    salt_level: Mapped[str] = mapped_column(String(16))  # light / medium / heavy
    token_cost: Mapped[int] = mapped_column(Integer, default=0)
```

### 3.4 IP 风格模型表
```python
class IPStyle(Base):
    __tablename__ = "ip_styles"
    style_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_name: Mapped[str] = mapped_column(String(128))  # 呼兰 / 鸟鸟 / 周奇墨
    version: Mapped[str] = mapped_column(String(32))      # v2.1
    description: Mapped[str] = mapped_column(Text)        # 风格特点说明
    prompt_snippet: Mapped[str] = mapped_column(Text)     # 注入 system prompt 的片段
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / testing / offline
    split_ratio: Mapped[int] = mapped_column(Integer, default=70)  # 演员分成比例
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
```

### 3.5 投稿表（用户 → 演员）
```python
class ScriptSubmission(Base):
    __tablename__ = "script_submissions"
    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey(...), index=True)
    script_id: Mapped[str] = mapped_column(ForeignKey("user_scripts.script_id"))
    target_actor: Mapped[str] = mapped_column(String(128))  # 投稿给哪位演员
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / adopted / rejected
    actor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### 3.6 收益记录表
```python
class EarningRecord(Base):
    __tablename__ = "earning_records"
    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey(...), index=True, nullable=True)  # 平台收益时为空
    actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    record_type: Mapped[str] = mapped_column(String(32))  # platform_fee / actor_split / withdrawal
    amount: Mapped[int] = mapped_column(Integer)  # 单位：分（或 Token 等价）
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### 3.7 敏感词配置表
```python
class BannedWord(Base):
    __tablename__ = "banned_words"
    word_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(128), unique=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # political / competitor / vulgar
    added_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

---

## 四、API 层扩展（`api/server.py`）

新增路由组，现有路由**不动**：

### 4.1 Token & 用户账户
- `GET /me/wallet` → 返回 Token 余额、累计消费、累计充值
- `POST /me/recharge` → 模拟充值（开发阶段）
- `POST /me/deduct` → 内部扣费（由 `/chat` 和 Skill 直调内部调用）

### 4.2 项目管理
- `GET /projects` → 列出用户项目
- `POST /projects` → 创建项目
- `GET /projects/{pid}` → 项目详情（含关联作品、加点盐历史）
- `PUT /projects/{pid}` → 重命名
- `DELETE /projects/{pid}` → 删除项目（级联删除关联记录）

### 4.3 加点盐（复用 `/chat`，但前端有独立入口）
- `POST /salt` → 接收 `{text, salt_level, project_id?}`
  - 内部构造 prompt：`"请对以下文本进行幽默润色，不改变原意，幽默程度约{salt_level}：\n\n{text}"`
  - 调用 `state.orch.run()`
  - 成功后扣费（light=10, medium=20, heavy=30 Token）
  - 保存到 `salt_history`
  - 返回 `{original, polished, token_cost}`

### 4.4 IP 风格模型
- `GET /ip-styles` → 列出所有上架中的 IP 风格（含 actor_name, description, usage_count）
- `GET /ip-styles/{style_id}` → 详情（含示例输出 prompt）
- `POST /ip-styles/{style_id}/use` → 记录一次使用（usage_count++）

### 4.5 投稿
- `POST /scripts/{script_id}/submit` → `{target_actor}`
- `GET /submissions` → 用户查看自己的投稿记录
- `GET /actor/submissions` → 演员/管理员查看待审核投稿（按 target_actor 过滤）
- `POST /submissions/{sid}/review` → `{status: adopted|rejected, comment?}`

### 4.6 演员工作台数据
- `GET /actor/dashboard` → 返回风格模型调用次数、预计收益、满意度、待审核数
- `GET /actor/earnings` → 收益明细
- `POST /actor/withdraw` → 申请提现

### 4.7 管理控制台
- `GET /admin/overview` → 平台概览（DAU、总生成次数、IP 调用次数、待结算分成）
- `GET /admin/skills/pending` → 待审核第三方 Skill 列表
- `POST /admin/skills/{name}/review` → 审核 Skill
- `GET /admin/ip-styles` → IP 模型列表（含分成比例、状态）
- `PUT /admin/ip-styles/{style_id}` → 编辑 IP 模型（状态、分成比例）
- `GET /admin/banned-words` → 敏感词列表
- `POST /admin/banned-words` → 添加敏感词
- `DELETE /admin/banned-words/{word_id}` → 删除敏感词

### 4.8 导出
- `GET /scripts/{script_id}/export?format=txt|md` → 返回文本文件下载

---

## 五、前端重构计划

### 5.1 页面结构重排

| 新页面 | 原型对应 | 说明 |
|-------|---------|------|
| `index.html` | 创作工坊 | **重写**：三栏布局，整合加点盐、喜剧创作、虚拟演员 |
| `login.html` | 登录/注册 | 小幅改动：增加品牌文案 "新用户注册即赠 5000 Token" |
| `projects.html` | 我的项目 | **新增**：项目管理入口（从 me.html 迁移） |
| `actor-dashboard.html` | 演员工作台 | **新增**：仅对签约 IP 角色可见 |
| `admin-console.html` | 管理控制台 | **新增**：仅管理员可见 |
| `ip-detail.html` | IP 风格详情 | **新增**：演员介绍页，支持分享链接 |
| `me.html` | 个人中心 | 简化：导航入口 + Token 余额展示 |
| `scripts.html` | 我的作品 | 保留，增加 "投稿给演员" 按钮 |
| `skills.html` | Skill 管理 | 保留，管理员增加 "审核" Tab |
| `knowledge.html` | 知识库 | 保留，不作大改 |
| `cards.html` | 技巧库 | 保留，不作大改 |

### 5.2 `index.html` 核心布局（原型复刻）

```
+----------------------------------------------------------+
|  Header: ComedyForge Logo | Token余额 | 我的 | 退出       |
+----------------------------------------------------------+
|  左侧边栏 (260px)  |  主区域 (flex)          | 右侧 (240px) |
|  ----------------  |  ---------------------  |  ----------- |
|  📁 我的项目       |  🧂 加点盐快捷卡片      |  🔥 热门IP   |
|    - 项目1         |    [微盐][中盐][重盐]   |    呼兰...   |
|    - 项目2         |    [输入框] [立即润色]  |    鸟鸟...   |
|  加点盐历史        |                         |  ----------- |
|  ----------------  |  🎤 喜剧创作区          |  📊 统计面板 |
|  💰 Token: 12,800  |    Skill + IP风格选择   |    今日生成  |
|  [充值]            |    主题 / 场景 / 彩蛋   |    你的收益  |
|                    |    [立即生成]           |              |
|                    |                         |              |
|                    |  📤 生成结果预览        |              |
|                    |    段子 / 语音彩蛋标签   |              |
|                    |    [投稿][导出][👍]     |              |
|                    |                         |              |
|                    |  🤖 虚拟演员Agent入口   |              |
|                    |    "与鸟鸟对话改稿"     |              |
+----------------------------------------------------------+
```

### 5.3 前端关键交互设计

- **加点盐**：独立 textarea + 三档选择器。点击"立即润色"调用 `/salt`，结果直接渲染在卡片下方，支持"保存到项目"。
- **IP 风格选择器**：下拉框选项来自 `GET /ip-styles`。选择后，在调用 `/chat` 或 `/skills/standup` 前，将 `ip_style_id` 对应的 `prompt_snippet` 作为 `system_hint` 注入请求。
- **虚拟演员 Agent**：点击后展开一个小型对话浮层，每轮调用 `/chat`，但在 prompt 前附加角色设定前缀。Token 消耗与普通对话一致。
- **投稿按钮**：作品生成后显示，点击弹出演员选择器（来自 `GET /ip-styles`），确认后调用 `POST /scripts/{id}/submit`。

---

## 六、不改动的核心链路清单

以下模块**完全不动**，新功能通过包装层复用：

1. `agent/orchestrator.py` —— Agent 主控逻辑
2. `models/factory.py` —— 模型工厂
3. `skills/*.py` —— 所有 Skill 实现
4. `rag/*.py` —— RAG 检索链路
5. `memory/unified.py` —— 统一记忆接口（仅透传新表操作）
6. `POST /chat` —— 对话主链路（新功能通过构造不同 prompt 复用）
7. `POST /skills/{standup,sketch,manzai,japanese-sketch}` —— Skill 直调接口

---

## 七、实施阶段建议

### 阶段 1：数据层 & API 层（基础设施）
- 新增 `memory/schema.py` 中的 7 张表
- 在 `memory/medium_term.py` 中增加对应 CRUD 方法
- 在 `api/server.py` 中注册新路由（`/salt`, `/projects`, `/ip-styles`, `/me/wallet`, `/submissions`, `/actor/*`, `/admin/*`, `/export`）
- 编写对应单元测试

### 阶段 2：前端核心页面（创作工坊）
- 重写 `index.html` 为三栏布局
- 实现加点盐卡片、喜剧创作区、虚拟演员入口
- 对接新 API：项目管理、IP 风格列表、Token 余额

### 阶段 3：业务功能页面
- 新建 `actor-dashboard.html`（演员工作台）
- 新建 `admin-console.html`（管理控制台）
- 新建 `ip-detail.html`（IP 风格详情）
- 改造 `scripts.html` 增加投稿和导出功能
- 改造 `skills.html` 增加管理员审核视图

### 阶段 4：联调 & 打磨
- Token 扣费逻辑端到端测试
- 加点盐效果验证（通过 prompt 工程）
- IP 风格注入效果验证
- 响应式布局适配

---

## 八、风险与应对

| 风险 | 应对 |
|-----|------|
| 大量新增 schema 导致旧数据库不兼容 | 使用 SQLAlchemy `create_all()` 自动创建新表；旧表不改动，兼容现有数据 |
| Token 扣费逻辑与现有测试冲突 | 新路由独立测试；在测试环境中注入 `mock` 的 Token 账户 |
| 前端 `index.html` 体积膨胀 | 按功能拆分为内嵌组件（原生 JS），不引入复杂构建工具 |
| IP 风格注入效果依赖 prompt 工程 | 初期用硬编码 `prompt_snippet`，不改动 Skill 内部，效果不佳可快速调整 |

---

## 九、最小可行路径（MVP）

若需快速验证，优先实现：
1. **Token 账户表** + `/me/wallet` 接口
2. **IP 风格表**（硬编码 3-4 条数据）+ `GET /ip-styles` 接口
3. **`/salt` 接口**（prompt 包装 + 扣费）
4. **重写 `index.html`**（三栏布局 + 加点盐 + IP 风格选择器 + Token 显示）

其余功能（投稿、收益、管理后台）可在 MVP 验证后再逐步叠加。
