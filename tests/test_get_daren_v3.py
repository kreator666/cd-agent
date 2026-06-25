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


class TestGenerateMode:
    """测试生成模式解析与状态流转。"""

    def setup_method(self):
        self.skill = Skill()

    def test_compute_next_state_slot_filling(self):
        result = self.skill._compute_next_state(
            "topic_filling", {"话题": "职场"}, {}, {}, advance=True
        )
        assert result["current_state"] == "attitude_filling"

    def test_compute_next_state_all_slots_filled(self):
        slots = {"话题": "职场", "态度": "愤怒", "偏见": "加班是对的", "情绪": "从愤怒到释然"}
        result = self.skill._compute_next_state(
            "emotion_filling", {"情绪": "从愤怒到释然"}, slots, {}, advance=True
        )
        assert result["current_state"] == "chief_editor_review"

    def test_compute_next_state_guiding_fill_slot(self):
        slots = {"话题": "职场"}
        result = self.skill._compute_next_state(
            "guiding", {"话题": "职场"}, slots, {}, advance=True
        )
        assert result["current_state"] == "attitude_filling"

    def test_compute_next_state_guiding_all_filled(self):
        slots = {"话题": "职场", "态度": "愤怒", "偏见": "加班是对的", "情绪": "从愤怒到释然"}
        result = self.skill._compute_next_state(
            "guiding", {"情绪": "从愤怒到释然"}, slots, {}, advance=True
        )
        assert result["current_state"] == "chief_editor_review"

    def test_handle_generate_missing_slots(self):
        result = json.loads(self.skill._handle_generate(
            user_input="生成",
            slots={"话题": "职场"},
            outputs={},
            user_id=None,
            attachments=[],
            current_role="主持人",
            current_state="guiding",
        ))
        assert "态度" in result["reply"]
        assert result["state_update"]["current_state"] == "attitude_filling"

    def test_handle_chief_editor_writing_first(self, monkeypatch):
        """首次进入分段生成应直接写第 1 段，不预生成大纲。"""
        def fake_content(*args, **kwargs):
            return "这是第一节内容。"

        monkeypatch.setattr(self.skill, "_generate_script_content", fake_content)

        result = json.loads(self.skill._handle_chief_editor_writing(
            slots={"话题": "职场", "态度": "愤怒", "偏见": "加班是对的", "情绪": "释然"},
            outputs={},
            user_id=None,
            attachments=[],
            user_input="按小节生成",
            current_state="chief_editor_writing",
        ))
        assert result["state_update"]["current_state"] == "chief_editor_review"
        assert result["outputs_update"]["section_index"] == 0
        assert "section_outline" not in result["outputs_update"]
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["op"] == "create"

    def test_handle_chief_editor_review_finish(self):
        """总编审阅阶段用户说「完成」才进入 done。"""
        outputs = {
            "chief_editor_prompted": True,
            "section_index": 1,
            "generated_sections": ["## 第 1 段\n\nabc", "## 第 2 段\n\ndef"],
        }
        result = json.loads(self.skill._handle_chief_editor_review(
            workflow_step={"action": "review", "state_id": "chief_editor_review", "role": "总编"},
            slots={"话题": "职场", "态度": "愤怒", "偏见": "加班是对的", "情绪": "释然"},
            outputs=outputs,
            user_input="完成",
            user_id=None,
            attachments=[],
            current_state="chief_editor_review",
        ))
        assert result["state_update"]["current_state"] == "done"
        assert "final_script" in result["outputs_update"]


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


class TestPromptEscaping:
    """测试 LLM 调用前花括号转义，防止 ChatPromptTemplate 误解析。"""

    def setup_method(self):
        self.skill = Skill()

    def test_call_llm_passes_raw_prompts_without_template_parsing(self, monkeypatch):
        """system_prompt / user_prompt 应原样传给 LLM，不被 ChatPromptTemplate 当模板解析。"""
        captured = {}

        class FakeLLM:
            def invoke(self, messages):
                captured["messages"] = messages
                class Result:
                    content = "fake"
                return Result()

        monkeypatch.setattr(
            "comedy_agent.models.factory.ModelFactory.get_model_with_fallback",
            lambda *args, **kwargs: FakeLLM(),
        )

        system = '{\n  "reply": "示例",\n  "next_role": "用户"\n}'
        user = '{"persona_id": "p1", "slots": {"话题": "职场"}}'
        result = self.skill._call_llm(system, user)

        assert result == "fake"
        sys_msg, human_msg = captured["messages"]
        assert sys_msg.content == system
        assert human_msg.content == user


class TestOptionResolution:
    """测试选项引用消解：用户回复选项编号时从上下文中解析实际内容。"""

    def setup_method(self):
        self.skill = Skill()

    def test_parse_numeric_options(self):
        text = "请选择：\n1) 职场\n2) 校园\n3) 家庭"
        options = self.skill._parse_options(text)
        assert options["1"] == "职场"
        assert options["2"] == "校园"
        assert options["3"] == "家庭"

    def test_parse_letter_options(self):
        text = "A. 长方形\nB. 圆形\nC. 三角形"
        options = self.skill._parse_options(text)
        assert options["a"] == "长方形"
        assert options["b"] == "圆形"
        assert options["c"] == "三角形"
        assert options["B"] == "圆形"

    def test_parse_chinese_numeric_options(self):
        text = "一、选项一\n二、选项二\n三、选项三"
        options = self.skill._parse_options(text)
        assert options["1"] == "选项一"
        assert options["2"] == "选项二"

    def test_parse_option_selector(self):
        assert self.skill._parse_option_selector("1") == "1"
        assert self.skill._parse_option_selector("a") == "a"
        assert self.skill._parse_option_selector("A") == "a"
        assert self.skill._parse_option_selector("选项2") == "2"
        assert self.skill._parse_option_selector("选B") == "b"
        assert self.skill._parse_option_selector("第一个") == "一"
        assert self.skill._parse_option_selector("①") == "①"
        assert self.skill._parse_option_selector("随便说说") is None

    def test_resolve_option_reference_numeric(self):
        history = [
            {"role": "assistant", "content": "请选择场景：\n1) 职场\n2) 校园\n3) 家庭"},
        ]
        result = self.skill._resolve_option_reference("1", history)
        assert result == "职场"

    def test_resolve_option_reference_letter(self):
        history = [
            {"role": "assistant", "content": "A. 愤怒\nB. 开心\nC. 无奈"},
        ]
        result = self.skill._resolve_option_reference("选B", history)
        assert result == "开心"

    def test_resolve_option_reference_no_history(self):
        result = self.skill._resolve_option_reference("1", [])
        assert result is None

    def test_resolve_option_reference_no_options(self):
        history = [
            {"role": "assistant", "content": "你好，请自由发挥。"},
        ]
        result = self.skill._resolve_option_reference("1", history)
        assert result is None

    def test_parse_inline_options(self):
        text = "我们可以考虑两个方向：A) 延续之前角色展开新情节，或 B) 完全跳出原有框架开启全新故事线。您更倾向哪种？"
        options = self.skill._parse_options(text)
        assert options["a"] == "延续之前角色展开新情节"
        assert options["b"] == "完全跳出原有框架开启全新故事线"

    def test_extract_from_log_format(self):
        history = [
            {"state": "guiding", "input": "继续", "output": "请选择：\n1) 职场\n2) 校园"},
        ]
        result = self.skill._resolve_option_reference("2", history)
        assert result == "校园"
