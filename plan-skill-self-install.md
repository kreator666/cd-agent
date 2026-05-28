# Skill 自安装能力 —— 开发计划

## 目标
让 Agent 具备运行时动态安装、卸载、热重载 Skill 的能力，补齐 Skill 生态的最后一块拼图。

---

## 一、任务拆分

### 任务 1：AgentOrchestrator 扩展（unregister + reload）

**修改文件**：`src/comedy_agent/agent/orchestrator.py`

- 新增 `unregister_skill(name: str) -> bool`
  - 从 `self.tools` 中移除指定 name 的 Skill
  - 使 Agent 缓存失效
  - 返回是否成功移除
- 新增 `reload_plugins(skills_dir: str | None = None) -> dict`
  - 重新扫描 `skills/` 目录
  - 对比当前已加载的 Skill，新增注册、移除已不存在的
  - 返回统计：added / removed / unchanged
- 新增 `list_skills() -> list[dict]` 增强
  - 返回更详细的 Skill 信息（来源：built-in / plugin / dynamic）

**工作量**：小

---

### 任务 2：后端 API 端点

**修改文件**：`src/comedy_agent/api/server.py`

- `POST /skills/install` — 安装新 Skill
  - 请求体：`{ "name": str, "skill_md": str, "prompt_txt": str, "skill_py": str | None }`
  - 安全校验：
    - `name` 只允许 `[a-zA-Z0-9_-]+`
    - `skill_py` 存在时做基础语法检查（`ast.parse`）
    - 禁止覆盖内置 Skill（reserved names）
  - 文件写入：在 `skills/` 下创建 `{name}/SKILL.md`、`{name}/prompt.txt`，可选 `skill.py`
  - 注册：调用 `state.orch.register_skill()` 或 `reload_plugins()`
  - 返回：安装成功的 Skill 信息

- `DELETE /skills/{name}` — 卸载 Skill
  - 安全校验：禁止卸载内置 Skill
  - 调用 `state.orch.unregister_skill(name)`
  - 删除 `skills/{name}/` 目录
  - 返回：成功/失败

- `POST /skills/reload` — 热重载所有插件
  - 调用 `state.orch.reload_plugins()`
  - 返回：重载统计

- 增强 `GET /skills`
  - 返回 Skill 列表，增加 `source` 字段（builtin / plugin）

**工作量**：中

---

### 任务 3：Loader 层热重载支持

**修改文件**：`src/comedy_agent/skills/loader.py`

- 重构 `load_plugin_skills()` 为可增量加载
- 新增 `scan_skills_dir(skills_dir)` — 仅扫描返回元数据列表，不注册
- 新增 `load_single_skill(skill_dir)` — 加载单个 Skill 目录并返回实例
- 确保重复加载同名 Skill 时不会重复注册（或自动覆盖）

**工作量**：小

---

### 任务 4：前端 Skill 管理面板

**修改文件**：`frontend/index.html`

在侧边栏新增「Skill 管理」折叠面板（可选，可后续迭代）：
- 显示当前已加载 Skill 列表（名称、来源、类型）
- 「安装 Skill」按钮：展开表单输入 SKILL.md 和 prompt.txt 内容
- 「热重载」按钮
- 对插件 Skill 显示「卸载」按钮

**工作量**：中（可选，本次可先不做，后续迭代）

---

### 任务 5：测试

- `test_agent_orchestrator.py` — 新增 unregister_skill / reload_plugins 测试
- `test_skills_loader.py` — 新增 load_single_skill / 热重载测试
- `test_api_server.py` — 新增 install / uninstall / reload 端点测试

**工作量**：小

---

## 二、实现顺序

```
1. Orchestrator 扩展（unregister + reload）
2. Loader 层热重载支持
3. 后端 API 端点（install / uninstall / reload）
4. 测试
5. 前端面板（可选，后续迭代）
```

## 三、关键设计决策

### 安全边界
- `skill_py` 代码执行前必须 `ast.parse` 通过
- 禁止覆盖内置 Skill（白名单机制）
- 写入路径严格限制在项目 `skills/` 目录下，禁止 `../` 路径穿越
- `name` 只允许 `[a-zA-Z0-9_-]+`，防止特殊字符导致文件系统问题

### 内置 Skill 白名单
```python
_BUILTIN_SKILLS = {
    "standup_generator", "crosstalk_generator", "sketch_generator",
    "sitcom_generator", "joke_analyzer", "script_evaluator",
}
```

### reload_plugins 策略
- 扫描 `skills/` 目录
- 对于新目录 → 加载并注册
- 对于已加载但目录已删除的 → unregister
- 对于已加载且目录仍存在 → 保持不变（不重复注册）
