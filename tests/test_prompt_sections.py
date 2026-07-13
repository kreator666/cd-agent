"""提示词段落解析工具测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from comedy_agent.skills.prompt_sections import (
    _chinese_number_to_int,
    build_system_prompt,
    build_user_input,
    extract_system_prompt_block,
    generate_combinations,
    load_skill_sections,
    parse_sections,
    section_id_from_title,
)


class TestChineseNumber:
    """中文数字转换测试。"""

    def test_arabic_digits(self):
        assert _chinese_number_to_int("12") == 12

    def test_chinese_digits(self):
        assert _chinese_number_to_int("二") == 2
        assert _chinese_number_to_int("十") == 10
        assert _chinese_number_to_int("十一") == 11


class TestSectionId:
    """章节 ID 生成测试。"""

    def test_chinese_prefix(self):
        assert section_id_from_title("# 二、五感幽默系统") == "sec-2"
        assert section_id_from_title("# 十一、最终原则") == "sec-11"

    def test_arabic_prefix(self):
        assert section_id_from_title("# 1. 引言") == "sec-1"

    def test_fallback(self):
        assert section_id_from_title("# 没有序号的标题").startswith("sec-")


class TestExtractSystemPromptBlock:
    """系统提示词区块提取测试。"""

    def test_extract_block(self):
        md = """---
name: test
---
## 系统提示词
```markdown
# 角色
你是一个助手。

# 一、规则
必须诚实。
```
## 提示词模板
请回答：{topic}
## 其他
无关内容
"""
        block = extract_system_prompt_block(md)
        assert "角色" in block
        assert "规则" in block
        assert "提示词模板" not in block
        assert "无关内容" not in block

    def test_missing_block(self):
        assert extract_system_prompt_block("# 纯标题\n无系统提示词") == ""


class TestParseSections:
    """章节解析测试。"""

    def test_basic_split(self):
        md = """## 角色定义
你是演员。

# 一、规则
必须搞笑。

# 二、技巧
使用反转。

# 最终原则
要真实。

【最终输出约束】
只输出正文。
"""
        intro, middle, outro = parse_sections(md)
        assert "角色定义" in intro
        assert len(middle) == 2
        assert middle[0][0] == "# 一、规则"
        assert middle[1][0] == "# 二、技巧"
        assert "最终原则" in outro
        assert "最终输出约束" in outro


class TestBuildUserInput:
    """用户输入格式化测试。"""

    def test_template_format(self):
        template = "话题：{topic}，态度：{attitude}"
        user_input = "话题：骨折 态度：自嘲"
        assert build_user_input(user_input, template) == "话题：骨折，态度：自嘲"

    def test_fallback(self):
        assert build_user_input("随便输入", "") == "随便输入"


class TestBuildSystemPrompt:
    """系统提示词组合测试。"""

    def test_combines_parts(self):
        intro = "intro"
        outro = "outro"
        sections = [("# 一、规则", "必须搞笑。")]
        prompt = build_system_prompt(intro, sections, outro)
        assert "intro" in prompt
        assert "# 一、规则" in prompt
        assert "必须搞笑" in prompt
        assert "outro" in prompt
        assert "--------------------------------------------------" in prompt


class TestLoadSkillSections:
    """Skill 章节加载测试。"""

    def test_standup_focused(self):
        data = load_skill_sections(Path("skills/standup_focused/SKILL.md"))
        assert data["intro"]
        assert data["outro"]
        assert len(data["sections"]) == 3
        ids = [s["id"] for s in data["sections"]]
        assert "sec-2" in ids
        assert "sec-4" in ids
        assert "sec-9" in ids

    def test_standup(self):
        data = load_skill_sections(Path("skills/standup/SKILL.md"))
        assert data["intro"]
        assert data["outro"]
        assert len(data["sections"]) == 10
        ids = [s["id"] for s in data["sections"]]
        assert "sec-1" in ids
        assert "sec-10" in ids


class TestGenerateCombinations:
    """章节排列组合测试。"""

    def test_all_nonempty_combinations(self):
        sections = [
            ("# 一、核心", "核心内容"),
            ("# 二、技巧", "技巧内容"),
            ("# 三、示例", "示例内容"),
        ]
        combos = generate_combinations(sections)
        # 3 个章节应生成 2^3 - 1 = 7 种非空组合
        assert len(combos) == 7
        labels = [label for _, label in combos]
        assert "comb_一" in labels
        assert "comb_一_二" in labels
        assert "comb_一_二_三" in labels

    def test_combination_depth(self):
        sections = [
            ("# 一、核心", "核心内容"),
            ("# 二、技巧", "技巧内容"),
            ("# 三、示例", "示例内容"),
        ]
        combos = generate_combinations(sections, combination_depth=2)
        # 只生成 1 个和 2 个章节的组合：C(3,1) + C(3,2) = 6
        assert len(combos) == 6
        assert all(len(combo) <= 2 for combo, _ in combos)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
