"""Agent Orchestrator —— 接收用户输入并路由到对应 Skill。

基于 LangChain 的 ``create_agent``（LangGraph）实现最简 Agent 主控。
"""

from __future__ import annotations

import json
import logging
import re
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

# 技能指定指令正则：匹配 "使用 xxx 技能" / "用 xxx 技能" / "使用 xxx"
_SKILL_DIRECTIVE_RE = re.compile(
    r"(?:使用|用)\s*(\w+)(?:\s*技能)?\s*(?:来|去)?\s*",
    re.IGNORECASE,
)

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
        同时注入知识库检索器，使 Skill 内部也能检索 RAG。
        """
        if isinstance(skill, ComedySkill):
            if self.model_name is not None:
                skill.model_name = self.model_name
            if self.retriever is not None:
                skill.retriever = self.retriever
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

    def debug_retrieval(
        self, query: str, user_id: str | None = None
    ) -> dict[str, Any]:
        """调试接口：返回知识库检索的完整中间结果。

        Returns:
            dict: 包含个人库结果、默认库结果、合并结果、Prompt 注入片段。
        """
        result: dict[str, Any] = {"query": query, "user_id": user_id}

        # 1. 个人知识库
        user_docs: list[Any] = []
        if user_id:
            user_docs = self._retrieve_user_knowledge(query, user_id, top_k=5)
        result["personal_docs"] = [
            {"content": d.page_content, "metadata": d.metadata}
            for d in user_docs
        ]

        # 2. 默认知识库
        default_docs: list[Any] = []
        if self.retriever is not None:
            try:
                default_docs = self.retriever.retrieve(query, top_k=5)
            except Exception as e:
                result["default_error"] = str(e)
        result["default_docs"] = [
            {"content": d.page_content, "metadata": d.metadata}
            for d in default_docs
        ]

        # 3. 合并去重
        all_docs = user_docs + default_docs
        seen: set[str] = set()
        unique_docs: list[Any] = []
        for doc in all_docs:
            key = doc.metadata.get("doc_id") or doc.page_content
            if key and key not in seen:
                seen.add(key)
                unique_docs.append(doc)
        result["merged_docs"] = [
            {"content": d.page_content, "metadata": d.metadata}
            for d in unique_docs[:6]
        ]

        # 4. 模拟 Prompt 注入片段
        if unique_docs:
            knowledge_lines: list[str] = []
            for idx, doc in enumerate(unique_docs[:6], 1):
                source = doc.metadata.get("source", "未知来源")
                text = doc.page_content.strip().replace("\n", " ")
                knowledge_lines.append(f"[{idx}] 来源: {source}\n{text}")
            knowledge_text = "\n\n".join(knowledge_lines)
            result["prompt_injection"] = (
                f"【知识库参考】\n"
                f"以下是与用户问题相关的喜剧行业知识，请在回答时参考：\n\n"
                f"{knowledge_text}\n"
                f"【知识库参考结束】"
            )
        else:
            result["prompt_injection"] = ""

        return result

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

    # ------------------------------------------------------------------ #
    # 技能指令解析与直接调用
    # ------------------------------------------------------------------ #
    def _parse_skill_directive(self, user_input: str) -> tuple[str | None, str]:
        """解析用户输入中的技能指定指令。

        匹配模式：
        - "使用 xxx 技能 来写..."
        - "用 xxx 技能 来写..."
        - "使用 xxx 来写..."

        Returns:
            (skill_name, actual_request)：skill_name 为 None 表示未指定技能。
        """
        match = _SKILL_DIRECTIVE_RE.search(user_input)
        if not match:
            return None, user_input

        skill_name = match.group(1)
        # 去掉匹配到的指令部分
        actual_request = user_input[: match.start()] + user_input[match.end() :]
        actual_request = actual_request.strip("，,。. ")
        return skill_name, actual_request

    def _find_skill(self, name: str) -> BaseTool | None:
        """按名称查找已注册的 Skill。"""
        for tool in self.tools:
            if getattr(tool, "name", None) == name:
                return tool
        return None

    def _extract_skill_args(
        self, skill: BaseTool, user_request: str
    ) -> dict[str, Any]:
        """用 LLM 将用户请求解析为技能参数。

        若解析失败则兜底：将用户请求作为第一个必填参数传入。
        """
        schema = getattr(skill, "args_schema", None)
        if schema is None:
            return {"input": user_request}

        # 收集参数描述
        params_info: list[str] = []
        first_required: str | None = None
        for field_name, field_info in schema.model_fields.items():
            if field_name in ("user_id",):
                continue
            desc = field_info.description or ""
            required = field_info.is_required()
            default = field_info.default
            if required and first_required is None:
                first_required = field_name
            req_mark = "(必填)" if required else f"(默认: {default})"
            params_info.append(f"- {field_name}: {desc} {req_mark}")

        if not params_info:
            return {"input": user_request}

        params_text = "\n".join(params_info)
        prompt = (
            f"将以下用户请求转换为 JSON 参数，严格按照技能参数要求输出。\n\n"
            f"技能参数要求：\n{params_text}\n\n"
            f"用户请求：{user_request}\n\n"
            f"请只输出合法的 JSON 对象，不要有任何解释或 Markdown 代码块标记。"
        )

        try:
            result = self.llm.invoke(
                [("system", "你是一个参数提取助手，只输出 JSON。"), ("human", prompt)]
            )
            content = str(result.content) if hasattr(result, "content") else str(result)

            # 尝试直接解析 JSON
            try:
                args = json.loads(content)
            except json.JSONDecodeError:
                # 尝试从 Markdown 代码块中提取
                code_match = re.search(
                    r"```(?:json)?\s*(.*?)```", content, re.DOTALL
                )
                if code_match:
                    args = json.loads(code_match.group(1).strip())
                else:
                    raise

            # 过滤掉 schema 中不存在的字段
            valid_fields = set(schema.model_fields.keys())
            args = {k: v for k, v in args.items() if k in valid_fields}
            return args
        except Exception:
            logger.warning(
                "LLM 参数解析失败，兜底处理：skill=%s, request=%s",
                skill.name,
                user_request[:100],
            )
            # 兜底：第一个必填参数
            if first_required:
                return {first_required: user_request}
            return {"input": user_request}

    def _invoke_directive_skill(
        self,
        skill: BaseTool,
        user_request: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """直接调用用户指定的 Skill。"""
        args = self._extract_skill_args(skill, user_request)
        if user_id is not None and "user_id" in getattr(
            skill, "args_schema", {}
        ).model_fields:
            args["user_id"] = user_id

        logger.info("直接调用指定 Skill: %s, args=%s", skill.name, args)
        output = skill.invoke(args)
        return {"output": output, "messages": []}

    def run(
        self,
        user_input: str,
        chat_history: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """接收用户输入，由 Agent 路由并执行对应 Skill。

        支持技能指定指令：用户输入中包含"使用 xxx 技能"时，
        直接调用对应 Skill，不走 Agent 自动路由。

        Args:
            user_input: 用户的自然语言输入。
            chat_history: 可选的历史消息列表，格式为 ``[(role, content), ...]``。
            user_id: 可选的用户标识，若配置了 memory 则会注入用户上下文。

        Returns:
            dict: 包含 ``output``（最终文本输出）和 ``messages``（完整消息链）的结果字典。
        """
        # 1. 检查是否指定了特定技能
        skill_name, actual_request = self._parse_skill_directive(user_input)
        if skill_name:
            skill = self._find_skill(skill_name)
            if skill is not None:
                return self._invoke_directive_skill(
                    skill, actual_request, user_id=user_id
                )
            # 技能未找到，继续走 Agent 路由并给出提示
            logger.warning("用户指定 Skill '%s' 未找到，回退到 Agent 路由", skill_name)

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
        """``run`` 的异步版本。

        支持技能指定指令：用户输入中包含"使用 xxx 技能"时，
        直接调用对应 Skill，不走 Agent 自动路由。
        """
        # 1. 检查是否指定了特定技能（同步解析即可）
        skill_name, actual_request = self._parse_skill_directive(user_input)
        if skill_name:
            skill = self._find_skill(skill_name)
            if skill is not None:
                return self._invoke_directive_skill(
                    skill, actual_request, user_id=user_id
                )
            logger.warning("用户指定 Skill '%s' 未找到，回退到 Agent 路由", skill_name)

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
