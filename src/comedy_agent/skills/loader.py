"""Skill 插件加载器 —— 从 skills/ 目录动态加载外部 Skill。

支持三种加载模式：
1. 声明式 Skill：SKILL.md → 自动生成 Tool（提示词内嵌在 Markdown 中）
2. 代码式 Skill：SKILL.md + skill.py → 导入自定义实现
3. 兼容模式：SKILL.md + prompt.txt → 旧版声明式（向后兼容）
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import yaml
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
        system_prompt: str = "",
        prompt_template: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.skill_dir = skill_dir
        self.task_type = task_type
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template
        self.metadata = metadata or {}

    @classmethod
    def from_markdown(cls, text: str, skill_dir: Path) -> "SkillMeta":
        """从 SKILL.md 文本解析元数据。

        支持两种格式：
        1. OKX 规范：YAML frontmatter + Markdown body
        2. 旧版格式：纯 Markdown，通过 ## 标题提取
        """
        # 尝试解析 YAML frontmatter
        frontmatter: dict[str, Any] = {}
        body = text

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
                body = fm_match.group(2)
            except yaml.YAMLError as e:
                logger.warning("YAML frontmatter 解析失败: %s，回退到旧版解析", e)
                frontmatter = {}

        # 从 frontmatter 或 body 中提取 name
        name = frontmatter.get("name", "")
        if not name:
            name_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            name = name_match.group(1).strip() if name_match else skill_dir.name

        # 从 frontmatter 或 body 中提取 description
        description = frontmatter.get("description", "")
        if not description:
            desc_match = re.search(
                r"^##\s+描述\s*\n+(.+?)(?=\n^##|\Z)", body, re.MULTILINE | re.DOTALL
            )
            description = (
                desc_match.group(1).strip().replace("\n", " ") if desc_match else name
            )

        # 从 frontmatter 或 body 中提取 task_type
        task_type = frontmatter.get("task_type", "")
        if not task_type:
            task_type = frontmatter.get("metadata", {}).get("task_type", "")
        if not task_type:
            task_match = re.search(
                r"^##\s+任务类型\s*\n+(.+?)(?=\n^##|\Z)", body, re.MULTILINE | re.DOTALL
            )
            if task_match:
                task_type = task_match.group(1).strip().lower()
                first_word = task_type.split()[0] if task_type.split() else "creative"
                if first_word in ("creative", "analytical", "fast"):
                    task_type = first_word
                else:
                    task_type = "creative"
            else:
                task_type = "creative"

        # 从 body 中提取参数表格
        parameters: list[dict[str, Any]] = []
        param_match = re.search(
            r"^##\s+参数\s*\n+(.*?)(\n^##|\Z)", body, re.MULTILINE | re.DOTALL
        )
        if param_match:
            table_text = param_match.group(1).strip()
            parameters = _parse_param_table(table_text)

        # 从 body 中提取系统提示词
        system_prompt = ""
        sp_match = re.search(
            r"^##\s+系统提示词\s*\n+```.*?\n(.*?)```",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if sp_match:
            system_prompt = sp_match.group(1).strip()
        else:
            # 尝试无代码块的格式
            sp_match2 = re.search(
                r"^##\s+系统提示词\s*\n+(.+?)(?=\n^##|\Z)",
                body,
                re.MULTILINE | re.DOTALL,
            )
            if sp_match2:
                system_prompt = sp_match2.group(1).strip()

        # 从 body 中提取提示词模板
        prompt_template = ""
        pt_match = re.search(
            r"^##\s+提示词模板\s*\n+```.*?\n(.*?)```",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if pt_match:
            prompt_template = pt_match.group(1).strip()
        else:
            pt_match2 = re.search(
                r"^##\s+提示词模板\s*\n+(.+?)(?=\n^##|\Z)",
                body,
                re.MULTILINE | re.DOTALL,
            )
            if pt_match2:
                prompt_template = pt_match2.group(1).strip()

        return cls(
            name=name,
            description=description,
            parameters=parameters,
            skill_dir=skill_dir,
            task_type=task_type,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
            metadata=frontmatter.get("metadata", {}),
        )


# ------------------------------------------------------------------ #
# Phase 3 SkillConfig 模型（供 Writer / state_modifier 使用）
# ------------------------------------------------------------------ #


class SkillExample(BaseModel):
    """Skill few-shot 示例。"""

    input: str = Field(default="", description="示例输入/上下文")
    output: str = Field(default="", description="示例输出")


class SkillConfig(BaseModel):
    """面向 Writer 的 Skill 配置。

    从新版 ``skill.yaml + system_prompt.md + examples/`` 读取，
    也可从旧版 ``SKILL.md`` 回退生成。
    """

    id: str = Field(description="Skill 目录标识符")
    name: str = Field(description="展示名称")
    description: str = Field(default="", description="简介")
    task_type: str = Field(default="creative", description="creative / analytical / fast")
    system_prompt: str = Field(default="", description="System Prompt 原始文本")
    prompt_template: str = Field(default="", description="用户层 Prompt 模板（可选）")
    examples: list[SkillExample] = Field(default_factory=list, description="Few-shot 示例")
    styles: list[str] = Field(default_factory=list, description="可用风格子选项")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")
    skill_dir: Path = Field(description="Skill 目录路径")


# ------------------------------------------------------------------ #
# 新版 Skill 文件加载
# ------------------------------------------------------------------ #


def _load_examples(examples_dir: Path) -> list[SkillExample]:
    """读取 examples/ 目录下的 JSON/Markdown 示例。"""
    examples: list[SkillExample] = []
    if not examples_dir.exists():
        return examples

    for path in sorted(examples_dir.iterdir()):
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("示例文件解析失败 %s: %s", path, e)
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    examples.append(
                        SkillExample(
                            input=str(item.get("input", "")),
                            output=str(item.get("output", "")),
                        )
                    )
        elif path.suffix.lower() in (".md", ".txt"):
            text = path.read_text(encoding="utf-8").strip()
            if text:
                examples.append(SkillExample(output=text))

    return examples


def _load_skill_yaml(skill_dir: Path) -> dict[str, Any] | None:
    """读取 skill.yaml，失败返回 None。"""
    yaml_path = skill_dir / "skill.yaml"
    if not yaml_path.exists():
        return None
    try:
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("skill.yaml 解析失败 %s: %s", yaml_path, e)
        return None


def _load_system_prompt(skill_dir: Path) -> str:
    """优先读取 system_prompt.md，其次 system_prompt.txt。"""
    for name in ("system_prompt.md", "system_prompt.txt"):
        path = skill_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def _load_prompt_template(skill_dir: Path) -> str:
    """优先读取 prompt_template.md，其次 prompt_template.txt。"""
    for name in ("prompt_template.md", "prompt_template.txt"):
        path = skill_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def load_skill_config(skill_dir: Path | str) -> SkillConfig | None:
    """加载单个 Skill 的配置（新格式优先，旧格式回退）。"""
    path = Path(skill_dir)
    if not path.is_dir():
        return None

    skill_id = path.name
    config = _load_skill_yaml(path)

    if config is not None:
        # 新版格式
        name = config.get("name") or skill_id
        description = config.get("description", "")
        task_type = config.get("task_type", "creative")
        styles = config.get("styles", []) or []
        metadata = config.get("metadata", {}) or {}
        system_prompt = _load_system_prompt(path)
        prompt_template = _load_prompt_template(path)
        examples = _load_examples(path / "examples")
    else:
        # 旧版 SKILL.md 回退
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return None
        try:
            meta = SkillMeta.from_markdown(skill_md.read_text(encoding="utf-8"), path)
        except Exception as e:
            logger.error("解析 %s 失败: %s", skill_md, e)
            return None
        name = meta.name
        description = meta.description
        task_type = meta.task_type
        styles = meta.metadata.get("styles", [])
        metadata = meta.metadata
        system_prompt = meta.system_prompt
        prompt_template = meta.prompt_template
        examples = _load_examples(path / "examples")

    return SkillConfig(
        id=skill_id,
        name=name,
        description=description,
        task_type=task_type,
        system_prompt=system_prompt,
        prompt_template=prompt_template,
        examples=examples,
        styles=styles,
        metadata=metadata,
        skill_dir=path,
    )


def load_skill_configs(skills_dir: Path | str | None = None) -> list[SkillConfig]:
    """扫描 Skill 目录，返回所有可识别的 SkillConfig。

    同时兼容新版 ``skill.yaml`` 与旧版 ``SKILL.md``。
    """
    if skills_dir is None:
        skills_dir = settings.skills_dir
    path = Path(skills_dir)
    if not path.exists():
        logger.info("Skill 目录不存在: %s", path)
        return []

    configs: list[SkillConfig] = []
    for subdir in sorted(path.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith(".") or subdir.name.startswith("__"):
            continue
        cfg = load_skill_config(subdir)
        if cfg is not None:
            configs.append(cfg)

    return configs


def get_default_skill_config(skills_dir: Path | str | None = None) -> SkillConfig:
    """返回默认 Skill，未找到时返回内置兜底配置。"""
    configs = load_skill_configs(skills_dir)
    for cfg in configs:
        if cfg.id == "standup_coach":
            return cfg
    # 兜底：与旧 Writer PROMPT 等价的默认配置
    return SkillConfig(
        id="default",
        name="默认写手",
        description="保留旧行为的默认脱口秀写手",
        task_type="creative",
        system_prompt=(
            "你是一位脱口秀写手。请根据用户提供的计划、已完成段落和反馈，"
            "撰写当前段落的正文。保持口语化、有画面感，适合舞台表演，"
            "不要解释笑点。"
        ),
        prompt_template="",
        examples=[],
        styles=[],
        metadata={},
        skill_dir=Path("."),
    )


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

    # 使用 SKILL.md 中的系统提示词，或回退到默认值
    _system_prompt = meta.system_prompt or (
        "你是一位专业的喜剧创作助手。请根据用户要求，"
        "严格按照给定的 Prompt 模板生成内容。"
    )

    class DeclarativeSkill(ComedySkill):
        name: str = meta.name
        description: str = meta.description
        args_schema: type[BaseModel] = _schema_cls
        task_type: str = meta.task_type

        SYSTEM_PROMPT: str = _system_prompt

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
            llm = ModelFactory.get_model_with_fallback(name=getattr(self, "model_name", None), task_type=getattr(self, "task_type", "creative"))
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

    # 将 meta 注入模块，让 skill.py 能访问 SKILL.md 解析结果
    module._skill_meta = meta  # type: ignore[attr-defined]

    # 必须先放入 sys.modules，否则 skill.py 中 sys.modules[__name__] 会 KeyError
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

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

    # 如果类没有 SYSTEM_PROMPT 且 meta 中有系统提示词，注入之
    if not getattr(skill_cls, "SYSTEM_PROMPT", None) and meta.system_prompt:
        skill_cls.SYSTEM_PROMPT = meta.system_prompt

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

        if not skill_md.exists():
            logger.debug("跳过 %s: 缺少 SKILL.md", subdir.name)
            continue

        # 解析元数据
        try:
            meta = SkillMeta.from_markdown(skill_md.read_text(encoding="utf-8"), subdir)
        except Exception as e:
            logger.error("解析 %s 失败: %s", skill_md, e)
            continue

        # 兼容旧版：如果存在 prompt.txt，用它覆盖 SKILL.md 中的模板
        prompt_txt = subdir / "prompt.txt"
        if prompt_txt.exists():
            meta.prompt_template = prompt_txt.read_text(encoding="utf-8")

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


# ------------------------------------------------------------------ #
# 安全校验
# ------------------------------------------------------------------ #

_BUILTIN_SKILL_NAMES = {
    "standup_generator",
    "crosstalk_generator",
    "sketch_generator",
    "sitcom_generator",
    "manzai_generator",
    "japanese_sketch_generator",
    "add_salt",
    "topic",
    "attitude",
    "emotion",
    "genre",
    "rule_persona",
    "script_composer",
    "material",
    "layout",
}


_SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def is_builtin_skill(name: str) -> bool:
    """判断是否为内置 Skill（禁止卸载/覆盖）。"""
    return name in _BUILTIN_SKILL_NAMES


def validate_skill_name(name: str) -> bool:
    """校验 Skill 名称合法性。"""
    return bool(_SKILL_NAME_PATTERN.match(name))


def validate_skill_py(code: str) -> bool:
    """校验 Python 代码语法合法性。"""
    import ast

    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


# ------------------------------------------------------------------ #
# 热重载支持
# ------------------------------------------------------------------ #


def scan_skills_dir(skills_dir: Path | str | None = None) -> list[Path]:
    """扫描 skills/ 目录，返回所有合法的 Skill 目录路径。"""
    if skills_dir is None:
        skills_dir = settings.skills_dir
    path = Path(skills_dir)
    if not path.exists():
        return []
    result: list[Path] = []
    for subdir in sorted(path.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith(".") or subdir.name.startswith("__"):
            continue
        if not (subdir / "SKILL.md").exists():
            continue
        result.append(subdir)
    return result


def load_single_skill(skill_dir: Path) -> ComedySkill | None:
    """加载单个 Skill 目录并返回实例。

    Args:
        skill_dir: Skill 目录路径。

    Returns:
        ComedySkill 实例，加载失败返回 None。
    """
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        logger.error("缺少 SKILL.md: %s", skill_dir)
        return None

    try:
        meta = SkillMeta.from_markdown(skill_md.read_text(encoding="utf-8"), skill_dir)
    except Exception as e:
        logger.error("解析 %s 失败: %s", skill_md, e)
        return None

    # 兼容旧版 prompt.txt
    prompt_txt = skill_dir / "prompt.txt"
    if prompt_txt.exists():
        meta.prompt_template = prompt_txt.read_text(encoding="utf-8")

    skill_py = skill_dir / "skill.py"
    try:
        if skill_py.exists():
            cls = _load_code_skill(skill_dir, meta)
            if cls is not None:
                logger.info("加载代码式 Skill: %s", meta.name)
                return cls()
        else:
            cls = _create_declarative_skill(meta)
            logger.info("加载声明式 Skill: %s", meta.name)
            return cls()
    except Exception as e:
        logger.error("加载 Skill %s 失败: %s", skill_dir.name, e)

    return None
