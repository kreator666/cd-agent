"""运行时上传文件的部署目录镜像。

上传接口把文件保存到仓库 ``frontend/`` 目录（本地开发、测试可用），
但生产环境 nginx 的 ``/static/`` 指向部署目录（``/var/www/frontend``），
因此需要把上传的文件镜像一份到部署目录才能通过 ``/static/`` URL 访问。

通过环境变量 ``STATIC_DEPLOY_DIR`` 启用；未配置（本地/测试）时跳过。
镜像写失败只记日志，不影响上传主流程。
"""

from __future__ import annotations

import logging
from pathlib import Path

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)


def mirror_upload(subdir: str, save_name: str, content: bytes) -> None:
    """把上传的文件镜像到 STATIC_DEPLOY_DIR 下的子目录。

    Args:
        subdir: 部署目录下的子目录名（如 "avatars"、"qr_codes"、"swap_images"）。
        save_name: 保存文件名。
        content: 文件字节内容。
    """
    if not settings.static_deploy_dir:
        return
    try:
        deploy_dir = Path(settings.static_deploy_dir) / subdir
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / save_name).write_bytes(content)
    except OSError as exc:
        logger.warning(
            "Mirror upload to deploy dir failed (%s/%s): %s", subdir, save_name, exc
        )
