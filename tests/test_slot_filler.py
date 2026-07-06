"""SlotFillingAgent 单元测试。"""

from langchain_core.messages import HumanMessage

from comedy_agent.agents.slot_filler import SlotFillingAgent
from comedy_agent.state.schema import ComedyState


def test_fill_single_slot():
    agent = SlotFillingAgent()
    result = agent.run(ComedyState(user_input="@话题 职场加班"))
    assert result["slots"] == {"话题": "职场加班"}
    assert result["active_slot_dimension"] == "话题"
    assert len(result["slot_conversations"]["话题"]) == 1
    assert isinstance(result["slot_conversations"]["话题"][0], HumanMessage)
    assert result["phase"] == "slot_checking"


def test_fill_multiple_slots():
    agent = SlotFillingAgent()
    result = agent.run(ComedyState(user_input="@话题 相亲 @态度 自嘲"))
    assert result["slots"]["话题"] == "相亲"
    assert result["slots"]["态度"] == "自嘲"
    assert result["active_slot_dimension"] == "态度"
    assert "话题" in result["slot_conversations"]
    assert "态度" in result["slot_conversations"]


def test_merge_with_existing_slots():
    agent = SlotFillingAgent()
    result = agent.run(
        ComedyState(
            user_input="@情绪 尴尬",
            slots={"话题": "加班", "态度": "讽刺"},
            slot_conversations={
                "话题": [HumanMessage(content="@话题 加班")]
            },
        )
    )
    assert result["slots"] == {
        "话题": "加班",
        "态度": "讽刺",
        "情绪": "尴尬",
    }
    assert len(result["slot_conversations"]["话题"]) == 1
    assert len(result["slot_conversations"]["情绪"]) == 1


def test_no_slot_mention():
    agent = SlotFillingAgent()
    result = agent.run(ComedyState(user_input="你好"))
    assert result["slots"] is None or result["slots"] == {}
    assert "active_slot_dimension" not in result
    assert "slot_conversations" not in result or not result["slot_conversations"]


def test_append_to_existing_slot():
    """同一维度多次 @ 时，应追加内容而不是覆盖。"""
    agent = SlotFillingAgent()
    result = agent.run(
        ComedyState(
            user_input="@话题 假如我有三千万",
            slots={},
        )
    )
    assert result["slots"]["话题"] == "假如我有三千万"

    result = agent.run(
        ComedyState(
            user_input="@话题 怕被绑架",
            slots=result["slots"],
        )
    )
    assert result["slots"]["话题"] == "假如我有三千万；怕被绑架"

    result = agent.run(
        ComedyState(
            user_input="@话题 肆意挥霍",
            slots=result["slots"],
        )
    )
    assert result["slots"]["话题"] == "假如我有三千万；怕被绑架；肆意挥霍"


def test_append_existing_substring():
    """新值与旧值有包含关系时，保留更完整的那份。"""
    agent = SlotFillingAgent()
    result = agent.run(
        ComedyState(
            user_input="@话题 加班",
            slots={"话题": "加班文化"},
        )
    )
    assert result["slots"]["话题"] == "加班文化"

    result = agent.run(
        ComedyState(
            user_input="@话题 加班文化",
            slots={"话题": "加班"},
        )
    )
    assert result["slots"]["话题"] == "加班文化"


def test_merge_avoids_duplicate_substring():
    """新值是旧值的子串或旧值包含新值时，避免无意义重复。"""
    agent = SlotFillingAgent()
    result = agent.run(
        ComedyState(
            user_input="@话题 加班",
            slots={"话题": "加班文化"},
        )
    )
    assert result["slots"]["话题"] == "加班文化"

    result = agent.run(
        ComedyState(
            user_input="@话题 加班文化",
            slots={"话题": "加班"},
        )
    )
    assert result["slots"]["话题"] == "加班文化"
