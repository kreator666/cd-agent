"""测试 pro_v4 接口对知识引用的透传。"""

from comedy_agent.api.routers.pro_v4 import _build_response
from comedy_agent.state.schema import ComedyState


class TestProV4Knowledge:
    """验证知识引用从 State 透传到响应 skill_meta。"""

    def test_final_script_response_includes_knowledge_references(self):
        state = ComedyState(
            phase="complete",
            output="最终剧本内容",
            response_type="script",
            skill_meta={
                "skill_id": "standup_coach",
                "skill_name": "脱口秀教练",
                "retrieved_examples_count": 2,
                "knowledge_references": [
                    {"id": "three-setup-four-punch", "title": "三番四抖", "category": "technique"}
                ],
            },
        )
        response = _build_response(state, session_id="sess-001")
        assert response.skill_meta is not None
        refs = response.skill_meta.get("knowledge_references", [])
        assert len(refs) == 1
        assert refs[0]["title"] == "三番四抖"

    def test_plan_review_response_extracts_knowledge_references(self):
        class FakeInterrupt:
            def __init__(self, value):
                self.value = value

        raw = {
            "__interrupt__": [
                FakeInterrupt(
                    {
                        "message": "计划已生成",
                        "outline": ["开头", "冲突", "结尾"],
                        "todo": ["分析", "写作"],
                        "tone": "讽刺",
                    }
                )
            ],
            "plan": {
                "outline": ["开头", "冲突", "结尾"],
                "todo": ["分析", "写作"],
                "tone": "讽刺",
                "knowledge_references": [
                    {"id": "callback", "title": "Callback", "category": "technique"}
                ],
            },
            "analysis": {"topic": "加班"},
        }
        response = _build_response(raw, session_id="sess-002")
        assert response.skill_meta is not None
        refs = response.skill_meta.get("knowledge_references", [])
        assert len(refs) == 1
        assert refs[0]["title"] == "Callback"

    def test_state_has_knowledge_fields(self):
        state = ComedyState(
            knowledge_references=[{"id": "x", "title": "X"}],
            knowledge_context=[{"title": "上下文"}],
        )
        assert state.knowledge_references is not None
        assert state.knowledge_context is not None
