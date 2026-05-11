"""Skill 插件加载器 —— 从 skills/ 目录动态加载外部 Skill。

支持两种加载模式：
1. 声明式 Skill：SKILL.md + prompt.txt → 自动生成 Tool
2. 代码式 Skill：SKILL.md + prompt.txt + skill.py → 导入自定义实现
"""

from __future__ import annotations

import importlib.util
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, create_model
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# SKILL.md 解析
# ------------------------------------------------------------------ #


class SkillMeta:
    """解析后的 Skill 元数据。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: list[dict[str, Any]],
        skill_dir: Path,
        task_type: str = "creative",
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.skill_dir = skill_dir
        self.task_type = task_type
        self.prompt_template: str = ""

    @classmethod
    def from_markdown(cls, text: str, skill_dir: Path) -> "SkillMeta":
        """从 SKILL.md 文本解析元数据。"""
        # 提取标题作为 name
        name_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else skill_dir.name

        # 提取 ## 描述 段落
        desc_match = re.search(
            r"^##\s+描述\s*\n+(.+?)(?=\n^##|\Z)", text, re.MULTILINE | re.DOTALL
        )
        description = (
            desc_match.group(1).strip().replace("\n", " ") if desc_match else name
        )

        # 提取任务类型
        task_type = "creative"
        task_match = re.search(
            r"^##\s+任务类型\s*\n+(.+?)(?=\n^##|\Z)", text, re.MULTILINE | re.DOTALL
        )
        if task_match:
            task_type = task_match.group(1).strip().lower()
            # 取第一行第一个有效词
            first_word = task_type.split()[0] if task_type.split() else "creative"
            if first_word in ("creative", "analytical", "fast"):
                task_type = first_word
            else:
                task_type = "creative"

        # 提取参数表格
        parameters: list[dict[str, Any]] = []
        param_match = re.search(
            r"^##\s+参数\s*\n+(.*?)(\n^##|\Z)", text, re.MULTILINE | re.DOTALL
        )
        if param_match:
            table_text = param_match.group(1).strip()
            parameters = _parse_param_table(table_text)

        return cls(name=name, description=description, parameters=parameters, skill_dir=skill_dir, task_type=task_type)


def _parse_param_table(table_text: str) -> list[dict[str, Any]]:
    """解析 Markdown 参数表格。"""
    parameters: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in table_text.splitlines() if ln.strip()]
    header_seen = False
    for line in lines:
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        # 跳过纯分隔符行
        if all(set(c) <= set("-: ") for c in cells):
            continue
        # 跳过表头行（第一个非分隔符的 | 行）
        if not header_seen:
            header_seen = True
            continue
        p_name = cells[0]
        p_type = cells[1].lower()
        p_required = cells[2].lower() in ("是", "true", "yes", "必填") if len(cells) > 2 else True
        p_desc = cells[3] if len(cells) > 3 else ""
        p_default = cells[4] if len(cells) > 4 else None
        parameters.append({
            "name": p_name,
            "type": p_type,
            "required": p_required,
            "description": p_desc,
            "default": p_default,
        })
    return parameters


# ------------------------------------------------------------------ #
# 动态 Args Schema 构建
# ------------------------------------------------------------------ #

_TYPE_MAP: dict[str, type] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "bool": bool,
    "boolean": bool,
}


def _build_args_schema(parameters: list[dict[str, Any]]) -> type[BaseModel]:
    """根据参数定义动态生成 Pydantic Model。"""
    fields: dict[str, Any] = {}
    for p in parameters:
        pname = p["name"]
        ptype = _TYPE_MAP.get(p["type"], str)
        desc = p.get("description", "")
        default = p.get("default")
        required = p.get("required", True)

        if default is not None:
            # 尝试类型转换
            try:
                if ptype is int:
                    default = int(default)
                elif ptype is float:
                    default = float(default)
                elif ptype is bool:
                    default = default.lower() in ("true", "yes", "1", "是")
            except (ValueError, AttributeError):
                default = None

        if required and default is None:
            fields[pname] = (ptype, Field(description=desc))
        else:
            fields[pname] = (ptype, Field(default=default if default is not None else "", description=desc))

    return create_model("DynamicSkillArgs", **fields)


# ------------------------------------------------------------------ #
# 动态 Skill 类生成
# ------------------------------------------------------------------ #


def _create_declarative_skill(meta: SkillMeta) -> type[ComedySkill]:
    """基于元数据和 prompt 模板生成动态 Skill 类。"""

    _schema_cls = _build_args_schema(meta.parameters)

    class DeclarativeSkill(ComedySkill):
        name: str = meta.name
        description: str = meta.description
        args_schema: type[BaseModel] = _schema_cls
        task_type: str = meta.task_type

        SYSTEM_PROMPT: str = (
            "你是一位专业的喜剧创作助手。请根据用户要求，"
            "严格按照给定的 Prompt 模板生成内容。"
        )

        def _run(self, **kwargs: Any) -> str:
            prompt_text = meta.prompt_template
            try:
                user_prompt = prompt_text.format(**kwargs)
            except KeyError as e:
                missing = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", str(e))
                user_prompt = prompt_text
                logger.warning("Prompt 模板变量缺失: %s", missing)

            prompt = ChatPromptTemplate.from_messages([
                ("system", self.SYSTEM_PROMPT),
                ("human", user_prompt),
            ])
            llm = ModelFactory.get_model_with_fallback(task_type=getattr(self, "task_type", "creative"))
            chain = prompt | llm
            result = chain.invoke({})
            return str(result.content) if hasattr(result, "content") else str(result)

        async def _arun(self, **kwargs: Any) -> str:
            return self._run(**kwargs)

    # 给类一个可读的名字，便于调试
    DeclarativeSkill.__name__ = f"{meta.name.replace(' ', '_')}Skill"
    DeclarativeSkill.__qualname__ = DeclarativeSkill.__name__
    return DeclarativeSkill


# ------------------------------------------------------------------ #
# 代码式 Skill 加载
# ------------------------------------------------------------------ #


def _load_code_skill(skill_dir: Path, meta: SkillMeta) -> type[ComedySkill] | None:
    """从 skill.py 动态导入自定义 Skill 类。"""
    skill_py = skill_dir / "skill.py"
    if not skill_py.exists():
        return None

    module_name = f"_dynamic_skill_{skill_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, skill_py)
    if spec is None or spec.loader is None:
        logger.error("无法加载 %s", skill_py)
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 优先查找名为 Skill 的类，或第一个继承 ComedySkill 的类
    skill_cls: type[ComedySkill] | None = getattr(module, "Skill", None)
    if skill_cls is None:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, ComedySkill)
                and attr is not ComedySkill
            ):
                skill_cls = attr
                break

    if skill_cls is None:
        logger.error("%s 中未找到继承 ComedySkill 的类", skill_py)
        return None

    # 如果类没有 name/description，用 meta 的填充
    if not getattr(skill_cls, "name", None):
        skill_cls.name = meta.name
    if not getattr(skill_cls, "description", None):
        skill_cls.description = meta.description

    return skill_cls


# ------------------------------------------------------------------ #
# 公共 API
# ------------------------------------------------------------------ #


def load_plugin_skills(skills_dir: Path | str | None = None) -> list[ComedySkill]:
    """扫描 skills/ 目录，加载所有合法的外部 Skill。

    Args:
        skills_dir: Skill 插件根目录，默认为 settings.skills_dir。

    Returns:
        list[ComedySkill]: 加载成功的 Skill 实例列表。
    """
    if skills_dir is None:
        skills_dir = settings.skills_dir
    path = Path(skills_dir)

    if not path.exists():
        logger.info("Skill 插件目录不存在: %s", path)
        return []

    loaded: list[ComedySkill] = []
    for subdir in sorted(path.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith(".") or subdir.name.startswith("__"):
            continue

        skill_md = subdir / "SKILL.md"
        prompt_txt = subdir / "prompt.txt"

        if not skill_md.exists():
            logger.debug("跳过 %s: 缺少 SKILL.md", subdir.name)
            continue

        # 解析元数据
        try:
            meta = SkillMeta.from_markdown(skill_md.read_text(encoding="utf-8"), subdir)
        except Exception as e:
            logger.error("解析 %s 失败: %s", skill_md, e)
            continue

        # 读取 prompt 模板
        if prompt_txt.exists():
            meta.prompt_template = prompt_txt.read_text(encoding="utf-8")
        else:
            logger.warning("%s 缺少 prompt.txt，将使用空模板", subdir.name)

        # 判断加载模式
        skill_py = subdir / "skill.py"
        try:
            if skill_py.exists():
                cls = _load_code_skill(subdir, meta)
                if cls is not None:
                    loaded.append(cls())
                    logger.info("加载代码式 Skill: %s", meta.name)
            else:
                cls = _create_declarative_skill(meta)
                loaded.append(cls())
                logger.info("加载声明式 Skill: %s", meta.name)
        except Exception as e:
            logger.error("加载 Skill %s 失败: %s", subdir.name, e)

    return loaded
