# Skills 插件目录

本目录用于存放插件化的喜剧 Skill。

每个 Skill 为一个子目录，包含：
- `SKILL.md`: Skill 元数据（名称、描述、输入输出定义）
- `prompt.txt`: 专家级 Prompt 模板
- `skill.py`: Skill 实现代码（可选，复杂逻辑时提供）

Agent 启动时会自动扫描本目录并注册所有合法 Skill。
