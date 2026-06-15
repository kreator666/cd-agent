# 素材 Skill —— 架构与流程介绍

> 分析日期：2026-06-15
> 分析范围：`skills/material/`、`src/comedy_agent/skills/material.py`

---

## 一、概述

**素材 Skill**（Material Skill）是 Comedy Agent 体系中的**分析型辅助 Skill**，用于根据用户输入的搜索词和当前创作话题，从外部 RSS 新闻源拉取最新文章，并通过大语言模型（LLM）整理为结构化的创作参考素材。

它的核心定位是：

- **搜索外部网络资料**：不依赖本地知识库，而是从可配置的 RSS 新闻源获取信息。
- **整理创作参考**：将原始搜索结果提炼为「标题 + 摘要 + 来源链接」的形式。
- **不替代用户创作**：只提供素材参考，不直接生成剧本或段子。

---

## 二、元数据声明

### 文件位置

`skills/material/SKILL.md`

### 声明内容

```yaml
---
name: material
description: "素材搜索。根据用户输入结合当前话题，搜索外部网络资料并整理为创作参考。不用于：直接生成剧本、替代用户创作。"
license: MIT
metadata:
  author: comedy-agent
  version: "1.0.0"
---
```

### 参数定义

| 参数名 | 类型 | 必填 | 描述 | 默认值 |
|--------|------|------|------|--------|
| `query` | `str` | 是 | 搜索关键词 | - |
| `topic` | `str` | 否 | 当前创作话题，用于扩展搜索意图 | `""` |
| `count` | `int` | 否 | 返回结果数量（最大 10） | `5` |

`SKILL.md` 中同时声明了系统提示词与提示词模板，与代码实现 `MaterialSkill` 保持一致。

---

## 三、类架构

### 继承关系

```
ComedySkill (src/comedy_agent/skills/base.py)
    └── MaterialSkill (src/comedy_agent/skills/material.py)
```

`ComedySkill` 继承自 `langchain_core.tools.BaseTool`，是所有 Skill 的抽象基类。`MaterialSkill` 只覆盖了最小必要接口，是一个轻量级的分析型工具 Skill。

### 核心类与模型

#### 1. `MaterialArgs` —— 参数校验模型

```python
class MaterialArgs(BaseModel):
    query: str = Field(description="搜索关键词")
    topic: str = Field(default="", description="当前创作话题，用于扩展搜索意图")
    count: int = Field(default=5, ge=1, le=10, description="返回结果数量（最大 10）")
```

- 使用 Pydantic 进行参数校验。
- `count` 限制在 `1~10` 之间。

#### 2. `MaterialSkill` —— Skill 实现

```python
class MaterialSkill(ComedySkill):
    task_type: str = "analytical"
    name: str = "material"
    available_styles: ClassVar[list[str]] = []
    description: str = "素材搜索。根据用户输入结合当前话题，从 RSS 新闻源获取创作参考素材。"
    args_schema: type[BaseModel] = MaterialArgs
```

关键属性说明：

| 属性 | 值 | 说明 |
|------|------|------|
| `task_type` | `"analytical"` | 走分析型模型分层配置 |
| `name` | `"material"` | Skill 唯一标识 |
| `args_schema` | `MaterialArgs` | 参数校验模型 |
| `model_name` | `None` | 未指定覆盖模型，使用分层默认模型 |

### 目录结构

```
skills/material/
├── SKILL.md          # Skill 元数据与提示词声明
└── skill.py          # 薄封装，复用内置 MaterialSkill

src/comedy_agent/skills/material.py
└── MaterialSkill     # 实际业务实现
```

`skills/material/skill.py` 仅做导入转发，使 `SKILL.md` 的元数据与 `src/comedy_agent/skills/material.py` 的实现保持一致：

```python
from comedy_agent.skills.material import MaterialSkill
__all__ = ["MaterialSkill"]
```

---

## 四、主要执行流程

### 流程概览

```
用户输入 (query + topic + count)
            │
            ▼
    构建搜索查询 _build_search_query
            │
            ▼
    RSS 拉取与筛选 _search / _search_rss
            │
            ▼
    有结果？ ── 否 ──▶ 返回「未搜索到相关素材」
            │
            是
            ▼
    LLM 整理 _format_results
            │
            ▼
    LLM 可用？ ── 否 ──▶ 兜底格式化 _fallback_format
            │
            是
            ▼
      返回结构化素材文本
```

### 1. 构建搜索查询

方法：`_build_search_query(query, topic)`

- 将 `query` 和 `topic` 去除空白后拼接。
- 若 `topic` 为空，则只使用 `query`。

示例：

| query | topic | 最终查询 |
|-------|-------|----------|
| `职场 PUA` | `互联网大厂` | `职场 PUA 互联网大厂` |
| `职场 PUA` | `""` | `职场 PUA` |

### 2. RSS 拉取与筛选

方法：`_search(query, count)` → `_search_rss(query, count)`

#### 数据源

素材 Skill 采用**双源搜索策略**：

1. **RSS 新闻源**：优先从配置的 RSS/Atom 源拉取结构化新闻，速度快、稳定、成本低。
2. **DuckDuckGo 网络搜索**：当 RSS 源无结果或结果不足时，自动通过网络搜索补充，覆盖生活、教育、小众话题等 RSS 源不包含的内容。

#### 数据源

从配置项 `settings.news_rss_feeds` 读取 RSS/Atom 源列表，逗号分隔。默认配置为：

```python
news_rss_feeds: str = Field(
    default=(
        "https://www.chinanews.com.cn/rss/scroll-news.xml,"
        "https://www.chinanews.com.cn/rss/china.xml,"
        "https://www.chinanews.com.cn/rss/world.xml,"
        "https://www.chinanews.com.cn/rss/finance.xml,"
        "https://www.ithome.com/rss/,"
        "https://36kr.com/feed,"
        "https://rss.mifaw.com/articles/5c8bb11a3c41f61efd36683e/5c919d543882afa09dff3fa3"
    ),
    alias="NEWS_RSS_FEEDS",
)
```

> 说明：默认池包含经过验证的中文 RSS 源，覆盖综合新闻（中新网）、科技（IT 之家）、创投（36 氪）与社会热点（知乎热榜）。相比旧版搜狐/新浪源，内容更及时，对"AI"、"职场"、"投资"等现代关键词匹配效果更好。

可通过环境变量 `NEWS_RSS_FEEDS` 覆盖。

#### 拉取过程

对每个订阅源：

1. 使用 `urllib.request` 发送 HTTP 请求，附带浏览器 User-Agent 与 Accept 头。
2. 检查响应 `Content-Type`，若返回纯 HTML 错误页则直接跳过。
3. 读取响应体，使用 `xml.etree.ElementTree` 解析。
4. 同时支持 RSS 2.0（根标签 `<rss>`）与 Atom 1.0（根标签 `<feed>`）：
   - RSS：遍历 `<channel>/<item>`，提取 `title`、`link`、`description`。
   - Atom：遍历 `<feed>/<entry>`，提取 `title`、`link/@href`、`summary`/`content`。
5. 按查询词做相关性过滤：
   - 将查询词按空格分词；
   - **优先按标题匹配**；标题未命中时，**仅按摘要前 500 字符匹配**；
   - 这样可以避免 36 氪「8 点 1 氪」、知乎热榜长回答等正文尾部包含大量无关关键词导致的误召回。
6. 收集到足够 `count` 条结果后提前返回。

#### 容错处理

- 若未配置 RSS 源，返回空列表。
- URL 清理：去除 URL 中所有空白字符，防止配置误输入空格导致 URL 非法。
- 单个源失败时，区分 `HTTPError`、`URLError`、`ParseError` 等记录 warning 并跳过，继续处理其他源。
- 网络请求超时为 10 秒。

### 3. 结果格式化

方法：`_format_results(results, query, topic, count)`

#### 原始结果拼接

将搜索结果拼接为文本块：

```
[1] 标题1
摘要1
来源：https://example.com/1

[2] 标题2
摘要2
来源：https://example.com/2
```

#### LLM 整理

调用 `ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)` 获取模型，构造提示词：

```
System:
你是一位资料整理助手。请将搜索到的新闻资料整理成结构化的创作参考。
每条素材需包含：标题、摘要、来源链接。
摘要控制在 100 字以内，突出与创作相关的关键信息。
只输出整理后的素材，不要额外解释。

Human:
搜索词：{query}
创作话题：{topic}

请根据以下搜索结果整理 {count} 条创作参考素材：

{search_text}
```

通过 LangChain 的 `ChatPromptTemplate` 构建链并调用，返回整理后的文本。

#### 兜底格式化

当 LLM 调用失败（无可用模型、网络异常等）时，使用 `_fallback_format` 输出：

```markdown
📚 参考素材：

1. **标题**
   摘要（前 120 字符）...
   来源：https://example.com
```

### 4. 无结果处理

若 `_search` 返回空列表，直接返回：

```
未搜索到相关素材，请尝试更换关键词或检查 RSS 源配置。
```

---

## 五、同步与异步执行

| 方法 | 说明 |
|------|------|
| `_run(query, topic, count, user_id)` | 同步执行入口 |
| `_arun(query, topic, count, user_id)` | 异步执行入口，默认委托给 `_run` |

当前实现中 RSS 拉取是同步网络 IO，因此异步版本也只是同步委托。后续如需优化，可将 RSS 拉取改造为异步。

---

## 六、关键配置项

| 配置 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `NEWS_RSS_FEEDS` | `.env` → `src/comedy_agent/core/config.py` | BBC / Guardian / 联合早报 RSS | RSS 源列表，逗号分隔 |
| `task_type` | `MaterialSkill.task_type` | `"analytical"` | 分析型模型分层 |
| `count` | 调用参数 | `5` | 返回条数，范围 `1~10` |

---

## 七、测试覆盖

测试文件：`tests/test_skills_material.py`

| 测试用例 | 覆盖点 |
|----------|--------|
| `test_build_search_query_with_topic` | query + topic 拼接 |
| `test_build_search_query_without_topic` | 仅 query |
| `test_search_rss_filters_by_query` | RSS 解析与关键词过滤 |
| `test_search_rss_empty_feeds` | 未配置 RSS 源时返回空 |
| `test_fallback_format` | 兜底格式化输出 |
| `test_run_returns_formatted_result` | `_run` 正常返回字符串 |
| `test_run_no_results` | 无结果时的提示 |
| `test_arun_delegates_to_run` | 异步委托同步 |

---

## 八、典型调用示例

### 直接调用

```python
from comedy_agent.skills.material import MaterialSkill

skill = MaterialSkill()
result = skill.run({
    "query": "职场 PUA",
    "topic": "互联网大厂",
    "count": 3,
})
print(result)
```

### 通过编排器调用

在 Agent 编排器中，通常以工具形式注册 `MaterialSkill`，由 LLM 根据用户意图自动选择调用，获取创作素材后再交给后续创作 Skill（如 `standup`、`sketch`）使用。

---

## 九、边界与限制

1. **依赖 RSS 源质量**：搜索结果完全取决于配置的 RSS 源内容与可达性。
2. **仅支持标题/摘要关键词匹配**：当前相关性过滤较为简单，没有做语义相似度排序。
3. **RSS 拉取为同步 IO**：异步场景下会阻塞事件循环。
4. **不保证链接可访问**：返回的 `href` 来自 RSS 源，可能失效或需要翻墙。
5. **结果上限 10 条**：由 `count` 参数限制，避免上下文过长。

---

## 十、未来可优化方向

1. **引入语义搜索**：对 RSS 条目做 Embedding 语义匹配，替代简单的关键词包含过滤。
2. **支持更多数据源**：除 RSS 外，可接入新闻 API、搜索引擎结果页等。
3. **异步化 RSS 拉取**：使用 `aiohttp` 并行拉取多个源，降低等待时间。
4. **结果去重与排序**：对跨源重复条目去重，并按相关性评分排序。
5. **缓存机制**：对热门查询结果做短期缓存，减少重复拉取。
