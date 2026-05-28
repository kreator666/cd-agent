"""Agent Orchestrator —— 接收用户输入并路由到对应 Skill。

基于 LangChain 的 ``create_agent``（LangGraph）实现最简 Agent 主控。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from comedy_agent.core.config import settings
from comedy_agent.core.observability import get_metrics, get_tracer
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelFactory
from comedy_agent.rag.vector_store import VectorStore
from comedy_agent.skills.base import ComedySkill

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "你是一个喜剧创作助手，擅长根据用户需求调用合适的创作工具完成脱口秀、相声、"
    "小品等喜剧内容的创作与分析。"
)


class AgentOrchestrator:
    """Agent 主控：最简 Orchestrator。

    负责管理 Skill（Tool）集合，构建 LangChain Agent，
    并将用户输入路由到合适的 Skill 执行。
    """

    def __init__(
        self,
        model_name: str | None = None,
        system_prompt: str | None = None,
        memory: UnifiedMemory | None = None,
        retriever: Any | None = None,
    ) -> None:
        """初始化 Orchestrator。

        Args:
            model_name: 模型标识，为 ``None`` 时使用 ``settings.default_model``。
            system_prompt: 系统提示词，覆盖默认值。
            memory: 可选的统一记忆接口，用于注入用户上下文。
            retriever: 可选的知识库混合检索器，用于根据用户查询注入相关知识。
        """
        self.model_name = model_name
        self.llm = ModelFactory.get_model(model_name)
        self.tools: list[BaseTool] = []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.memory = memory
        self.retriever = retriever
        self._agent: Any | None = None
        self._user_vector_stores: dict[str, VectorStore] = {}

    # ------------------------------------------------------------------ #
    # Skill 管理
    # ------------------------------------------------------------------ #
    def register_skill(self, skill: BaseTool) -> None:
        """注册 Skill（Tool）。

        注册新 Skill 后会重置内部 Agent 缓存，下次 ``run`` 时自动重建。
        如果 Orchestrator 指定了 model_name，会同步传播给 ComedySkill。
        """
        if isinstance(skill, ComedySkill) and self.model_name is not None:
            skill.model_name = self.model_name
        self.tools.append(skill)
        self._agent = None
        logger.info("Registered skill: %s", skill.name)

    def unregister_skill(self, name: str) -> bool:
        """注销指定 Skill。

        Args:
            name: Skill 名称标识。

        Returns:
            是否成功移除。
        """
        for i, tool in enumerate(self.tools):
            if tool.name == name:
                self.tools.pop(i)
                self._agent = None
                logger.info("Unregistered skill: %s", name)
                return True
        logger.warning("Skill not found for unregister: %s", name)
        return False

    def reload_plugins(self, skills_dir: str | None = None) -> dict[str, int]:
        """热重载所有插件 Skill。

        扫描 skills/ 目录，对比当前已加载的插件：
        - 新增：磁盘上有但 tools 中没有的 → 加载并注册
        - 移除：tools 中有但磁盘上已不存在的 → 注销
        - 不变：两者都有的 → 保持不变

        Args:
            skills_dir: Skill 插件根目录，默认使用 settings.skills_dir。

        Returns:
            dict: {added, removed, unchanged} 统计。
        """
        from comedy_agent.skills.loader import (
            load_single_skill,
            scan_skills_dir,
        )

        scanned = scan_skills_dir(skills_dir)
        scanned_names = {p.name for p in scanned}
        current_plugin_names = {
            t.name for t in self.tools if getattr(t, "name", None) not in _BUILTIN_SKILL_NAMES
        }

        added = 0
        removed = 0

        # 移除已不存在的插件
        for name in list(current_plugin_names):
            if name not in scanned_names:
                if self.unregister_skill(name):
                    removed += 1

        # 注册新插件
        for skill_dir in scanned:
            if skill_dir.name not in current_plugin_names:
                skill = load_single_skill(skill_dir)
                if skill is not None:
                    self.register_skill(skill)
                    added += 1

        unchanged = len(scanned_names & current_plugin_names)
        logger.info("Reload plugins: added=%d, removed=%d, unchanged=%d", added, removed, unchanged)
        return {"added": added, "removed": removed, "unchanged": unchanged}

    def list_skills(self) -> list[dict[str, Any]]:
        """返回已注册的所有 Skill 详细信息列表。"""
        from comedy_agent.skills.loader import _BUILTIN_SKILL_NAMES

        result = []
        for tool in self.tools:
            info: dict[str, Any] = {
                "name": tool.name,
                "description": getattr(tool, "description", ""),
                "task_type": getattr(tool, "task_type", "creative"),
                "source": "builtin" if tool.name in _BUILTIN_SKILL_NAMES else "plugin",
            }
            result.append(info)
        return result

    # ------------------------------------------------------------------ #
    # Agent 构建与执行
    # ------------------------------------------------------------------ #
    def set_model(self, model_name: str | None) -> None:
        """运行时切换模型。

        Args:
            model_name: 新模型标识，为 ``None`` 时使用默认模型。
        """
        if model_name == self.model_name:
            return
        self.model_name = model_name
        self.llm = ModelFactory.get_model(model_name)
        self._agent = None  # 强制重建 Agent
        # 同步更新已注册 Skill 的模型
        for skill in self.tools:
            if isinstance(skill, ComedySkill):
                skill.model_name = model_name
        logger.info("模型已切换至: %s", model_name)

    def _build_agent(self) -> Any:
        """构建或复用 LangChain Agent（CompiledStateGraph）。"""
        if self._agent is not None:
            return self._agent

        self._agent = create_agent(
            model=self.llm,
            tools=self.tools or None,
            system_prompt=self.system_prompt,
        )
        logger.debug(
            "Agent built with %d tool(s): %s",
            len(self.tools),
            self.list_skills(),
        )
        return self._agent

    def _get_user_vector_store(self, user_id: str) -> VectorStore:
        """获取或创建用户的个人知识库向量存储。"""
        if user_id not in self._user_vector_stores:
            self._user_vector_stores[user_id] = VectorStore(
                collection_name=f"user_knowledge_{user_id}",
                persist_path=str(settings.vector_db_path),
            )
        return self._user_vector_stores[user_id]

    def _retrieve_user_knowledge(
        self, query: str, user_id: str, top_k: int = 3
    ) -> list[Any]:
        """检索用户个人知识库。"""
        try:
            store = self._get_user_vector_store(user_id)
            return store.search(query, top_k=top_k)
        except Exception:
            logger.debug("用户个人知识库检索失败", exc_info=True)
            return []

    def _build_system_prompt(
        self, user_input: str, user_id: str | None = None
    ) -> str:
        """构建完整的 System Prompt，整合基础提示 + 用户记忆 + 知识库。

        Args:
            user_input: 用户当前输入，用于知识库检索。
            user_id: 可选的用户标识，用于注入用户记忆。

        Returns:
            完整的 System Prompt 文本。
        """
        parts: list[str] = [self.system_prompt]

        # 1. 注入用户记忆
        if self.memory and user_id:
            memory_text = self.memory.build_context_text(user_id)
            if memory_text:
                parts.append(
                    f"【关于用户】\n"
                    f"以下是该用户的历史偏好与创作习惯，请在回答时参考：\n\n"
                    f"{memory_text}\n"
                    f"【关于用户结束】"
                )

        # 2. 注入知识库检索结果（个人库优先 + 默认库）
        all_docs: list[Any] = []

        # 2.1 用户个人知识库
        if user_id:
            user_docs = self._retrieve_user_knowledge(user_input, user_id, top_k=3)
            all_docs.extend(user_docs)

        # 2.2 默认知识库
        if self.retriever is not None:
            try:
                default_docs = self.retriever.retrieve(user_input, top_k=5)
                all_docs.extend(default_docs)
            except Exception:
                logger.debug("默认知识库检索失败，跳过注入", exc_info=True)

        # 去重并格式化
        if all_docs:
            seen: set[str] = set()
            unique_docs: list[Any] = []
            for doc in all_docs:
                key = doc.metadata.get("doc_id") or doc.page_content
                if key and key not in seen:
                    seen.add(key)
                    unique_docs.append(doc)

            knowledge_lines: list[str] = []
            for idx, doc in enumerate(unique_docs[:6], 1):
                source = doc.metadata.get("source", "未知来源")
                text = doc.page_content.strip().replace("\n", " ")
                knowledge_lines.append(f"[{idx}] 来源: {source}\n{text}")
            knowledge_text = "\n\n".join(knowledge_lines)
            parts.append(
                f"【知识库参考】\n"
                f"以下是与用户问题相关的喜剧行业知识，请在回答时参考：\n\n"
                f"{knowledge_text}\n"
                f"【知识库参考结束】"
            )

        return "\n\n".join(parts)

    def run(
        self,
        user_input: str,
        chat_history: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """接收用户输入，由 Agent 路由并执行对应 Skill。

        Args:
            user_input: 用户的自然语言输入。
            chat_history: 可选的历史消息列表，格式为 ``[(role, content), ...]``。
            user_id: 可选的用户标识，若配置了 memory 则会注入用户上下文。

        Returns:
            dict: 包含 ``output``（最终文本输出）和 ``messages``（完整消息链）的结果字典。
        """
        tracer = get_tracer()
        metrics = get_metrics()

        with tracer.span(
            "agent.run",
            input_data={"user_input": user_input[:200], "user_id": user_id},
            metadata={
                "model": self.model_name,
                "skills": self.list_skills(),
            },
        ) as span:
            agent = self._build_agent()

            messages: list[Any] = []

            # 构建并注入完整的 System Prompt（基础提示 + 用户记忆 + 知识库）
            system_prompt = self._build_system_prompt(user_input, user_id)
            messages.append(("system", system_prompt))

            if chat_history:
                for role, content in chat_history:
                    messages.append((role, content))
            messages.append(("human", user_input))

            result = agent.invoke({"messages": messages})

            # 提取最后一条 AI 消息作为输出
            msg_list: list[BaseMessage] = result.get("messages", [])
            output = ""
            for msg in reversed(msg_list):
                if isinstance(msg, AIMessage):
                    output = str(msg.content)
                    break

            span.output_data = {"output": output[:200]}
            metrics.record("agent.run.duration_ms", span.duration_ms)
            metrics.record(
                "agent.run.tokens",
                len(str(msg_list)),
                tags={"model": self.model_name or "unknown"},
            )

            return {
                "output": output,
                "messages": msg_list,
            }

    async def arun(
        self,
        user_input: str,
        chat_history: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """``run`` 的异步版本。"""
        tracer = get_tracer()
        metrics = get_metrics()

        with tracer.span(
            "agent.arun",
            input_data={"user_input": user_input[:200], "user_id": user_id},
            metadata={"model": self.model_name, "skills": self.list_skills()},
        ) as span:
            agent = self._build_agent()

            messages: list[Any] = []

            system_prompt = self._build_system_prompt(user_input, user_id)
            messages.append(("system", system_prompt))

            if chat_history:
                for role, content in chat_history:
                    messages.append((role, content))
            messages.append(("human", user_input))

            result = await agent.ainvoke({"messages": messages})

            msg_list: list[BaseMessage] = result.get("messages", [])
            output = ""
            for msg in reversed(msg_list):
                if isinstance(msg, AIMessage):
                    output = str(msg.content)
                    break

            span.output_data = {"output": output[:200]}
            metrics.record("agent.arun.duration_ms", span.duration_ms)

            return {
                "output": output,
                "messages": msg_list,
            }
