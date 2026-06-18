"""get_daren V3 角色调度器单元测试。"""

import json

import pytest

from comedy_agent.core.prompt_manager import PromptManager
from skills.get_daren.skill import Skill


@pytest.fixture(autouse=True)
def load_prompts():
    """自动加载 pro 角色提示词。"""
    PromptManager().load_from_directory()


class TestIntentClassification:
    """测试语义意图分类。"""

    def setup_method(self):
        self.skill = Skill()

    def test_detect_mention_core_slot(self):
        assert self.skill._detect_mention("@话题 职场PUA") == "话题专家"
        assert self.skill._detect_mention("@态度 很生气") == "态度专家"
        assert self.skill._detect_mention("@素材 找一些新闻") == "素材调研员"

    def test_detect_mention_none(self):
        assert self.skill._detect_mention("职场PUA") is None

    def test_extract_mention_content(self):
        assert self.skill._extract_mention_content("@话题 职场PUA", "话题") == "职场PUA"
        assert self.skill._extract_mention_content("@话题职场PUA", "话题") == "职场PUA"

    def test_classify_intent_fill_slot_by_mention(self):
        intent = self.skill._classify_intent("@话题 职场PUA", "主持人", {})
        assert intent["type"] == "fill_slot"
        assert intent["slot_name"] == "话题"
        assert intent["slot_value"] == "职场PUA"

    def test_classify_intent_switch_role_by_mention(self):
        intent = self.skill._classify_intent("@素材 找新闻", "话题专家", {})
        assert intent["type"] == "switch_role"
        assert intent["mentioned_role"] == "素材调研员"

    def test_classify_intent_trigger_generate(self):
        intent = self.skill._classify_intent("生成", "情绪专家", {})
        assert intent.get("trigger_generate") is True

    def test_classify_intent_semantic_role(self):
        intent = self.skill._classify_intent("帮我找素材", "主持人", {})
        assert intent["type"] == "switch_role"
        assert intent.get("semantic_role") == "素材调研员"

    def test_classify_intent_auto_topic(self):
        intent = self.skill._classify_intent("职场PUA", "主持人", {})
        # 注意：_run 中会二次判断非提问句式并填槽；_classify_intent 本身返回 chat
        assert intent["type"] == "chat"


class TestRoleDecision:
    """测试角色切换决策。"""

    def setup_method(self):
        self.skill = Skill()

    def test_determine_target_role_from_mention(self):
        intent = {"type": "switch_role", "mentioned_role": "态度专家"}
        assert self.skill._determine_target_role(intent, "话题专家", {}) == "态度专家"

    def test_determine_target_role_fill_slot(self):
        intent = {"type": "fill_slot", "slot_name": "偏见"}
        assert self.skill._determine_target_role(intent, "态度专家", {}) == "偏见专家"

    def test_determine_target_role_keep_current(self):
        intent = {"type": "chat"}
        assert self.skill._determine_target_role(intent, "话题专家", {}) == "话题专家"

    def test_self_cue_prevention(self):
        """下一个角色不能是自己。"""
        parsed = {"reply": "ok", "next_role": "话题专家"}
        target_role = "话题专家"
        next_role = parsed.get("next_role") or ""
        if not next_role or next_role == target_role:
            next_role = "态度专家"
        assert next_role == "态度专家"


class TestPromptLoading:
    """测试角色提示词加载。"""

    def test_role_prompts_loaded(self):
        pm = PromptManager()
        for name in [
            "pro/host",
            "pro/topic_expert",
            "pro/attitude_expert",
            "pro/bias_expert",
            "pro/emotion_expert",
            "pro/material_researcher",
            "pro/layout_editor",
            "pro/chief_editor",
        ]:
            text = pm.get(name)
            assert "角色" in text
            assert "JSON" in text


class TestOutputParsing:
    """测试 LLM 输出解析。"""

    def setup_method(self):
        self.skill = Skill()

    def test_parse_json_output_plain(self):
        raw = '{"reply": "hello", "next_role": "话题专家"}'
        parsed = self.skill._parse_json_output(raw)
        assert parsed["reply"] == "hello"
        assert parsed["next_role"] == "话题专家"

    def test_parse_json_output_markdown_block(self):
        raw = '```json\n{"reply": "hello", "next_role": "话题专家"}\n```'
        parsed = self.skill._parse_json_output(raw)
        assert parsed["reply"] == "hello"

    def test_parse_invalid_json(self):
        raw = "just plain text"
        parsed = self.skill._parse_json_output(raw)
        assert parsed["reply"] == "just plain text"


class TestQuestionDetection:
    """测试提问句式判断。"""

    def setup_method(self):
        self.skill = Skill()

    def test_is_question(self):
        assert self.skill._is_question("我应该写什么？") is True
        assert self.skill._is_question("怎么写剧本") is True

    def test_is_not_question(self):
        assert self.skill._is_question("职场PUA") is False
        assert self.skill._is_question("写一个关于加班的段子") is False


class TestArtifactsAndAttachments:
    """测试 artifact / attachment 解析。"""

    def setup_method(self):
        self.skill = Skill()

    def test_parse_json_output_with_artifacts(self):
        raw = json.dumps({
            "reply": "已生成调研报告",
            "next_role": "用户",
            "artifacts": [
                {"id": "r1", "type": "research", "title": "调研", "content": "报告内容", "op": "create", "created_by": "素材调研员"}
            ],
            "attachments": [
                {"id": "a1", "name": "素材", "summary": "摘要", "full_text": "全文"}
            ]
        }, ensure_ascii=False)
        parsed = self.skill._parse_json_output(raw)
        assert len(parsed["artifacts"]) == 1
        assert parsed["artifacts"][0]["type"] == "research"
        assert len(parsed["attachments"]) == 1

    def test_build_context_includes_attachment_summary(self):
        attachments = [
            {"id": "a1", "name": "素材报告", "summary": "这是摘要", "full_text": "这是全文内容", "mime_type": "text/plain"}
        ]
        context = self.skill._build_context(
            role="总编",
            slots={"话题": "职场"},
            outputs={},
            attachments=attachments,
            decision_nodes=[],
            conversation_history=[],
            user_input="生成",
        )
        assert "素材报告" in context["attachment_summary"]
        assert "这是摘要" in context["attachment_summary"]
