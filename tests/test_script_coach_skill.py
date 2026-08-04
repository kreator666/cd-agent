"""script_coach Skill 单元测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def skill_module():
    """动态加载 script_coach/skill.py 模块（与 loader 机制一致）。"""
    module_name = "_test_script_coach_skill"
    # 强制重新加载，避免旧代码缓存
    sys.modules.pop(module_name, None)
    skill_py = (
        Path(__file__).resolve().parents[1] / "skills" / "script_coach" / "skill.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, skill_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def skill(skill_module):
    """返回 ScriptCoachSkill 实例。"""
    return skill_module.ScriptCoachSkill()


class TestScriptCoachSkill:
    """测试段子教练 Skill 的核心逻辑。"""

    def test_skill_metadata(self, skill):
        """Skill 元数据正确。"""
        assert skill.name == "script_coach"
        assert "教练" in skill.description
        assert skill.task_type == "analytical"

    def test_args_schema_fields(self, skill):
        """参数 Schema 包含关键字段且限制正确。"""
        schema = skill.args_schema
        fields = schema.model_fields
        assert "script" in fields
        assert "topic" in fields
        assert "iterations" in fields
        assert fields["iterations"].default == 1
        assert schema(iterations=5, script="x", topic="t").iterations == 5
        # 运行时会被强制限制为 5，schema 本身允许更大的输入用于测试

    @patch("_test_script_coach_skill.VectorStore")
    @patch("_test_script_coach_skill.ModelFactory.get_model_with_fallback")
    def test_single_round_evaluation(self, mock_get_model, mock_vector_store_class, skill, skill_module):
        """单轮评分返回正确结构。"""
        mock_store = MagicMock()
        mock_store.search.return_value = []
        mock_vector_store_class.return_value = mock_store

        mock_scores = skill_module.DimensionScores(
            humor_score=6.0,
            setup_quality=7.0,
            punchline_quality=6.5,
            pacing=7.0,
            colloquial_score=7.5,
            resonance=8.0,
            surprise=6.0,
            observation=7.0,
            structure_integrity=7.5,
            performance_readiness=7.0,
        )

        mock_diagnosis = skill_module.DiagnosisOutput(
            gap_to_top="铺垫稍长",
            weaknesses=["铺垫可压缩", "笑点密度不足"],
            improvement_plan="压缩铺垫并增加一个反转",
        )

        mock_llm = MagicMock()

        def structured_side_effect(schema_cls):
            if schema_cls.__name__ == "DimensionScores":
                structured = MagicMock()
                structured.invoke.return_value = mock_scores
                return structured
            if schema_cls.__name__ == "DiagnosisOutput":
                structured = MagicMock()
                structured.invoke.return_value = mock_diagnosis
                return structured
            return MagicMock()

        mock_llm.with_structured_output.side_effect = structured_side_effect
        mock_get_model.return_value = mock_llm

        output = skill.invoke(
            {
                "script": "大家好，今天聊聊加班。",
                "topic": "加班",
                "style": "自嘲",
                "iterations": 1,
                "min_score": 8.0,
                "save_product": False,
            }
        )

        result = json.loads(output)
        assert "final_script" in result
        assert "iterations" in result
        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["round"] == 1
        assert result["stopped_reason"] == "达到最大迭代轮数 1"

    @patch("_test_script_coach_skill.VectorStore")
    @patch("_test_script_coach_skill.ModelFactory.get_model_with_fallback")
    def test_iterations_capped_at_5(self, mock_get_model, mock_vector_store_class, skill, skill_module):
        """迭代轮数被限制为最大 5。"""
        mock_store = MagicMock()
        mock_store.search.return_value = []
        mock_vector_store_class.return_value = mock_store

        mock_scores = skill_module.DimensionScores(
            **{k: 5.0 for k in [
                "humor_score", "setup_quality", "punchline_quality", "pacing",
                "colloquial_score", "resonance", "surprise", "observation",
                "structure_integrity", "performance_readiness",
            ]}
        )

        mock_diagnosis = skill_module.DiagnosisOutput(
            gap_to_top="一般",
            weaknesses=["改进点"],
            improvement_plan="再改改",
        )

        mock_llm = MagicMock()

        def structured_side_effect(schema_cls):
            if schema_cls.__name__ == "DimensionScores":
                structured = MagicMock()
                structured.invoke.return_value = mock_scores
                return structured
            if schema_cls.__name__ == "DiagnosisOutput":
                structured = MagicMock()
                structured.invoke.return_value = mock_diagnosis
                return structured
            return MagicMock()

        mock_llm.with_structured_output.side_effect = structured_side_effect
        mock_get_model.return_value = mock_llm

        output = skill.invoke(
            {
                "script": "大家好。",
                "topic": "测试",
                "iterations": 10,
                "min_score": 10.0,
                "save_product": False,
            }
        )

        result = json.loads(output)
        assert len(result["iterations"]) == 5

    @patch("_test_script_coach_skill.VectorStore")
    @patch("_test_script_coach_skill.ModelFactory.get_model_with_fallback")
    def test_early_stop_by_min_score(self, mock_get_model, mock_vector_store_class, skill, skill_module):
        """达到 min_score 时提前终止。"""
        mock_store = MagicMock()
        mock_store.search.return_value = []
        mock_vector_store_class.return_value = mock_store

        mock_scores = skill_module.DimensionScores(
            **{k: 8.5 for k in [
                "humor_score", "setup_quality", "punchline_quality", "pacing",
                "colloquial_score", "resonance", "surprise", "observation",
                "structure_integrity", "performance_readiness",
            ]}
        )

        mock_diagnosis = skill_module.DiagnosisOutput(
            gap_to_top="已接近顶流",
            weaknesses=[],
            improvement_plan="无需改写",
        )

        mock_llm = MagicMock()

        def structured_side_effect(schema_cls):
            if schema_cls.__name__ == "DimensionScores":
                structured = MagicMock()
                structured.invoke.return_value = mock_scores
                return structured
            if schema_cls.__name__ == "DiagnosisOutput":
                structured = MagicMock()
                structured.invoke.return_value = mock_diagnosis
                return structured
            return MagicMock()

        mock_llm.with_structured_output.side_effect = structured_side_effect
        mock_get_model.return_value = mock_llm

        output = skill.invoke(
            {
                "script": "非常好的段子。",
                "topic": "成功",
                "iterations": 3,
                "min_score": 8.0,
                "save_product": False,
            }
        )

        result = json.loads(output)
        assert len(result["iterations"]) == 1
        assert "达到 min_score" in result["stopped_reason"]

    def test_format_references_with_data(self, skill, skill_module):
        """参考文稿格式化包含关键信息。"""
        refs = [
            skill_module.ReferenceInfo(
                source="专场A.txt", topic="加班", style="自嘲", humor_score=9.0, snippet="铺垫..."
            )
        ]
        text = skill._format_references(refs)
        assert "专场A.txt" in text
        assert "9.0" in text
        assert "加班" in text

    def test_format_references_empty(self, skill):
        """空参考库返回兜底提示。"""
        text = skill._format_references([])
        assert "顶流文稿库为空" in text

    def test_save_product_to_memory(self, skill, skill_module):
        """最终作品保存到用户作品库，且不写入顶流库。"""
        mock_memory = MagicMock()
        mock_memory.save_script.return_value = MagicMock(script_id="script_123")
        skill.memory = mock_memory

        mock_store = MagicMock()
        mock_store.search.return_value = []

        mock_scores = skill_module.DimensionScores(
            **{k: 8.5 for k in [
                "humor_score", "setup_quality", "punchline_quality", "pacing",
                "colloquial_score", "resonance", "surprise", "observation",
                "structure_integrity", "performance_readiness",
            ]}
        )

        mock_diagnosis = skill_module.DiagnosisOutput(
            gap_to_top="已接近顶流",
            weaknesses=[],
            improvement_plan="无需改写",
        )

        mock_llm = MagicMock()

        def structured_side_effect(schema_cls):
            if schema_cls.__name__ == "DimensionScores":
                structured = MagicMock()
                structured.invoke.return_value = mock_scores
                return structured
            if schema_cls.__name__ == "DiagnosisOutput":
                structured = MagicMock()
                structured.invoke.return_value = mock_diagnosis
                return structured
            return MagicMock()

        mock_llm.with_structured_output.side_effect = structured_side_effect

        with patch.object(skill_module, "VectorStore", return_value=mock_store):
            with patch.object(skill_module, "ModelFactory") as mock_factory:
                mock_factory.get_model_with_fallback.return_value = mock_llm
                output = skill.invoke(
                    {
                        "script": "测试段子。",
                        "topic": "测试",
                        "iterations": 1,
                        "min_score": 8.0,
                        "save_product": True,
                        "user_id": "user_001",
                    }
                )

        result = json.loads(output)
        assert result["saved_script_id"] == "script_123"
        mock_memory.save_script.assert_called_once()
        call_args = mock_memory.save_script.call_args
        assert call_args[0][0] == "user_001"
        saved_script_data = call_args[0][1]
        assert saved_script_data.content == "测试段子。"
