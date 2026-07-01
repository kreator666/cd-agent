"""Supervisor 样例引导写作路由测试。"""

from __future__ import annotations

from comedy_agent.agents.supervisor import SupervisorAgent
from comedy_agent.state.schema import ComedyState


def test_writing_routes_to_example_generator_in_manual_mode():
    agent = SupervisorAgent()
    state = ComedyState(phase="writing", manual_section_mode=True)
    assert agent.route(state) == "example_generator"


def test_writing_routes_to_writer_when_manual_mode_off():
    agent = SupervisorAgent()
    state = ComedyState(phase="writing", manual_section_mode=False)
    assert agent.route(state) == "writer"


def test_generating_examples_routes_to_example_generator():
    agent = SupervisorAgent()
    state = ComedyState(phase="generating_examples")
    assert agent.route(state) == "example_generator"


def test_example_review_routes_to_example_review_node():
    agent = SupervisorAgent()
    state = ComedyState(phase="example_review")
    assert agent.route(state) == "example_review"
