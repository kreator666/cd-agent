"""Prompt 模板工程化模块 —— 统一管理、版本控制与 A/B 测试。

支持：
- 内存注册 / 文件加载 / 目录批量加载
- Jinja2 变量注入（自动 fallback 到 str.format）
- 多版本管理（v1 / v2 / ...）
- A/B 测试流量分配
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import Any

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# 延迟导入 Jinja2，未安装时降级到 str.format
try:
    from jinja2 import Template as JinjaTemplate
    from jinja2 import UndefinedError

    _HAS_JINJA = True
except ImportError:
    _HAS_JINJA = False
    logger.warning("jinja2 未安装，Prompt 渲染将使用 str.format()，部分高级语法不可用")


class PromptNotFoundError(Exception):
    """指定的 Prompt 名称或版本不存在。"""


class PromptManager:
    """Prompt 管理器。

    以 ``{name: {version: template}}`` 的结构存储所有 Prompt 模板，
    支持运行时动态注册、文件热加载和 A/B 测试。
    """

    _instance: PromptManager | None = None
    _store: dict[str, dict[str, str]]

    def __new__(cls) -> PromptManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store = {}
        return cls._instance

    # ------------------------------------------------------------------ #
    # 注册与加载
    # ------------------------------------------------------------------ #

    def register(
        self, name: str, template: str, version: str = "default"
    ) -> None:
        """在内存中注册一个 Prompt 模板。

        Args:
            name: Prompt 标识名，如 ``standup_system``。
            template: 模板文本，支持 Jinja2 语法或 ``{var}`` 占位符。
            version: 版本号，默认 ``default``。
        """
        if name not in self._store:
            self._store[name] = {}
        self._store[name][version] = template
        logger.debug("Registered prompt '%s' version '%s'", name, version)

    def load_from_file(
        self,
        path: Path | str,
        name: str | None = None,
        version: str = "default",
    ) -> None:
        """从单个文件加载 Prompt 模板。

        Args:
            path: 文件路径。
            name: Prompt 标识名，默认使用文件名（不含扩展名）。
            version: 版本号。
        """
        p = Path(path)
        if not p.exists():
            raise PromptNotFoundError(f"Prompt 文件不存在: {p}")

        template = p.read_text(encoding="utf-8")
        key = name or p.stem
        self.register(key, template, version)

    def load_from_directory(self, dir_path: Path | str | None = None) -> int:
        """批量加载目录下的所有 ``.txt`` / ``.md`` 文件。

        文件命名约定：
        - ``{name}.txt`` / ``{name}.md`` → 注册为 ``name`` 的 ``default`` 版本
        - ``{name}_v2.txt`` / ``{name}_v2.md`` → 注册为 ``name`` 的 ``v2`` 版本
        - ``{name}/default.txt`` / ``{name}/default.md`` → 注册为 ``name`` 的 ``default`` 版本

        Args:
            dir_path: Prompt 目录，默认为 ``settings.data_dir / "prompts"``。

        Returns:
            int: 成功加载的模板数量。
        """
        if dir_path is None:
            dir_path = settings.data_dir / "prompts"
        root = Path(dir_path)
        if not root.exists():
            logger.info("Prompt 目录不存在: %s", root)
            return 0

        loaded = 0
        prompt_files = sorted(root.rglob("*.txt")) + sorted(root.rglob("*.md"))
        for f in prompt_files:
            relative = f.relative_to(root)
            # 处理子目录结构：name/version.txt
            parts = relative.with_suffix("").parts
            if len(parts) >= 2:
                name = "/".join(parts[:-1])
                version = parts[-1]
            else:
                # 处理文件名结构：name_v2.txt 或 name.txt
                stem = f.stem
                m = re.match(r"^(.*)_(v\d+)$", stem)
                if m:
                    name, version = m.group(1), m.group(2)
                else:
                    name, version = stem, "default"

            try:
                self.load_from_file(f, name=name, version=version)
                loaded += 1
            except Exception as e:
                logger.error("加载 Prompt 文件 %s 失败: %s", f, e)

        logger.info("从 %s 加载了 %d 个 Prompt 模板", root, loaded)
        return loaded

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, name: str, version: str = "default") -> str:
        """获取指定 Prompt 的原始模板文本。

        Args:
            name: Prompt 标识名。
            version: 版本号。

        Raises:
            PromptNotFoundError: 名称或版本不存在。
        """
        versions = self._store.get(name)
        if not versions:
            raise PromptNotFoundError(f"Prompt '{name}' 未注册")
        if version not in versions:
            available = ", ".join(versions.keys())
            raise PromptNotFoundError(
                f"Prompt '{name}' 版本 '{version}' 不存在。可用版本: {available}"
            )
        return versions[version]

    def list_versions(self, name: str) -> list[str]:
        """返回指定 Prompt 的所有版本号列表。"""
        versions = self._store.get(name, {})
        return sorted(versions.keys())

    def list_prompts(self) -> list[str]:
        """返回所有已注册的 Prompt 名称列表。"""
        return sorted(self._store.keys())

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #

    def render(
        self, name: str, variables: dict[str, Any] | None = None, version: str = "default"
    ) -> str:
        """渲染 Prompt 模板，注入变量。

        若模板包含 Jinja2 语法（``{{`` / ``{%``）则优先使用 Jinja2 渲染；
        否则使用 ``str.format()``。若渲染失败，自动降级或保留占位符。

        Args:
            name: Prompt 标识名。
            variables: 变量字典。
            version: 版本号。

        Returns:
            str: 渲染后的文本。
        """
        template = self.get(name, version)
        variables = variables or {}

        if _HAS_JINJA and ("{{" in template or "{%" in template):
            try:
                return JinjaTemplate(template, trim_blocks=True, lstrip_blocks=True).render(**variables)
            except UndefinedError:
                pass
            except Exception as e:
                logger.warning("Jinja2 渲染失败，降级到 str.format(): %s", e)

        # 使用 str.format()（兼容 {var} 占位符）
        try:
            return template.format(**variables)
        except KeyError as e:
            missing = str(e)
            logger.warning("Prompt 变量缺失 %s，保留原始占位符", missing)
            return template

    # ------------------------------------------------------------------ #
    # A/B 测试
    # ------------------------------------------------------------------ #

    def get_ab_version(
        self,
        name: str,
        config: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> str:
        """根据流量配置随机选择一个版本，用于 A/B 测试。

        Args:
            name: Prompt 标识名。
            config: 版本 → 流量比例的字典，如 ``{"default": 0.8, "v2": 0.2}``。
                为 ``None`` 时，所有已注册版本均分流量。
            seed: 随机种子，用于可复现的测试。

        Returns:
            str: 选中的版本号。
        """
        versions = self.list_versions(name)
        if not versions:
            raise PromptNotFoundError(f"Prompt '{name}' 未注册，无法进行 A/B 测试")

        if config is None:
            # 均分
            weights = {v: 1.0 / len(versions) for v in versions}
        else:
            weights = {v: config.get(v, 0.0) for v in versions}

        total = sum(weights.values())
        if total <= 0:
            return versions[0]

        normalized = {v: w / total for v, w in weights.items()}

        rng = random.Random(seed)
        r = rng.random()
        cumulative = 0.0
        for v, w in normalized.items():
            cumulative += w
            if r <= cumulative:
                return v

        return versions[-1]

    def render_ab(
        self,
        name: str,
        variables: dict[str, Any] | None = None,
        config: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> tuple[str, str]:
        """A/B 测试快捷方法：返回选中的版本号及渲染后的文本。

        Returns:
            tuple[str, str]: (版本号, 渲染后文本)
        """
        version = self.get_ab_version(name, config=config, seed=seed)
        text = self.render(name, variables=variables, version=version)
        return version, text
