# v4 Skill 系统设计文档

## 1. 目标
让 v4 LangGraph 创作流水线支持**运行时切换**的 Skill 系统：
- Writer Agent 根据用户选择或 `@提及` 加载不同 Skill。
- 每个 Skill 包含 System Prompt、可选的用户 Prompt 模板、Few-shot 示例。
- 新增/修改 Skill 无需重启服务即可生效。

## 2. Skill 文件格式

每个 Skill 是一个独立目录，支持新版格式：

```text
skills/{skill_id}/
  skill.yaml          # 元数据
  system_prompt.md    # System Prompt（Jinja2 模板）
  prompt_template.md  # 可选：用户层 Prompt 模板
  examples/           # Few-shot 示例
    01.json
    02.json
    ...
```

### 2.1 skill.yaml

```yaml
id: zhou_qimo
name: 周奇墨风格
description: 观察式脱口秀，娓娓道来，注重细节铺陈。
task_type: creative
styles: []
metadata:
  kind: standup
  comedian: 周奇墨
```

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | Skill 目录标识符，同时是路由与 UI 使用的 ID。 |
| `name` | 展示名称。 |
| `description` | 简介。 |
| `task_type` | `creative` / `analytical` / `fast`，影响模型选择。 |
| `styles` | 风格子选项列表（可选）。 |
| `metadata` | 任意附加元数据；`kind: standup` 表示写作类 Skill。 |

### 2.2 system_prompt.md

支持 Jinja2 变量：

- `{{ style }}` —— 当前选中的风格子选项。
- `{{ user_input }}` —— 用户原始输入。
- `{{ section_goal }}` —— 当前段落目标。
- `{{ feedback_section }}` —— 人类审阅反馈。
- `{{ section_index }}` —— 当前段落序号（从 1 开始）。

### 2.3 examples/*.json

每条示例格式：

```json
[
  {
    "input": "主题：加班。段落目标：描述加班到深夜的场景。",
    "output": "那天晚上十一点，整个办公室只剩我和空调。"
  }
]
```

一个 JSON 文件可以是单条对象，也可以是对象数组。

## 3. Loader API

### `comedy_agent.core.skill_loader`

```python
from comedy_agent.core.skill_loader import (
    SkillConfig,
    load_skill_config,
    load_skill_configs,
    get_default_skill_config,
)

# 加载单个 Skill
cfg = load_skill_config("skills/zhou_qimo")

# 加载全部
cfgs = load_skill_configs()

# 获取默认 Skill（优先 my_skill，否则内置兜底）
default = get_default_skill_config()
```

### 向后兼容

旧版 `skills/{name}/SKILL.md + skill.py` 仍然通过 `load_plugin_skills()` 加载为 `ComedySkill` 工具，供 `/skills/*`、`/pro/chat` 等路径使用。

## 4. Prompt 构建

`graph/state_modifier.py` 负责将 `ComedyState` 与 `SkillConfig` 组装为四层 Prompt：

1. **基础角色层**：固定中文喜剧创作助手角色。
2. **Skill system_prompt 层**：渲染 Skill 的 `system_prompt.md`。
3. **Few-shot 示例层**：拼接 `examples/` 中的示例。
4. **用户上下文层**：当前 outline、段落目标、已完成段落、反馈等。

若 Skill 未提供 `prompt_template.md`，则使用默认 Writer 上下文模板。

## 5. Skill 路由

`core/skill_router.py` 以**代码条件**决定 `selected_skill` / `selected_style`：

优先级：
1. UI 显式传入 `skill_id` / `style`。
2. 用户输入中的 `@提及`，如 `@周奇墨`、`@hu_lan`。
3. `ComedyState` 中已保存的 `selected_skill` / `selected_style`。
4. 兜底 `my_skill`。

别名映射：

| 提及 | Skill ID |
|---|---|
| @周奇墨 | zhou_qimo |
| @徐志胜 | xu_zhisheng |
| @呼兰 | hu_lan |
| @默认 / @我的默认风格 | my_skill |
| @开源 / @开源通用技巧 | open_source_skill |

非写作类 Skill（如 `@话题`）不会被误判为写作 Skill。

## 6. UI 入口

`frontend/pro-b.html`：
- 顶部槽位状态条下方显示当前选中的写作风格徽章。
- 「写作团队」下拉菜单中新增「写作风格」区域，列出 `/pro/skills` 返回的 `skill_type == "writing"` 的 Skill。
- 选中后随 `/pro/chat-v4` 请求发送 `skill_id` / `style`。

## 7. 已提供的风格化 Skill

| Skill ID | 名称 | 特点 |
|---|---|---|
| `my_skill` | 我的默认风格 | 口语化、有画面感、默认行为等价于旧 Writer。 |
| `open_source_skill` | 开源通用技巧 | Setup/Punchline、Callback、三段式等通用技巧。 |
| `zhou_qimo` | 周奇墨风格 | 观察式、娓娓道来、细节铺陈。 |
| `xu_zhisheng` | 徐志胜风格 | 自嘲、外形梗、热情高能量。 |
| `hu_lan` | 呼兰风格 | 高密度文本、金融/职场隐喻、快节奏。 |

## 8. 测试

- `tests/test_skills_loader.py`：新/旧格式加载、兜底配置。
- `tests/test_state_modifier.py`：四层 Prompt 构建。
- `tests/test_writer.py`：Writer 按 Skill 生成。
- `tests/test_skill_router.py`：路由规则。
- `tests/test_skills_styles.py`：3 个风格化 Skill 加载与 Prompt 差异。

## 9. 里程碑 M3 验收标准

- [x] 用户可在 UI 选择不同 Skill。
- [x] Writer Agent 生成不同风格的 Prompt（至少 3 种风格可区分）。
- [x] 切换 Skill 无需重启服务。
- [x] 相关测试全部通过。
