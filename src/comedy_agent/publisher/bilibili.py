"""
B站 (bilibili) 平台适配器。

基于 bilitool 库实现视频投稿。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from comedy_agent.publisher.base_adapter import BasePlatformAdapter
from comedy_agent.publisher.models import ContentItem, PlatformType, PublishResult

logger = logging.getLogger(__name__)


class BilibiliAdapter(BasePlatformAdapter):
    """B站适配器 - 基于 bilitool 库。"""

    platform_type = PlatformType.BILIBILI

    # B站分区ID映射（常用分区）
    TID_MAPPING = {
        "动画": 1,
        "番剧": 13,
        "国创": 167,
        "音乐": 3,
        "舞蹈": 129,
        "游戏": 4,
        "知识": 36,
        "科技": 188,
        "运动": 234,
        "汽车": 223,
        "生活": 160,
        "美食": 211,
        "动物圈": 217,
        "鬼畜": 119,
        "时尚": 155,
        "娱乐": 5,
        "影视": 181,
        "纪录片": 177,
        "电影": 23,
        "电视剧": 11,
    }

    # 默认分区: 生活-日常
    DEFAULT_TID = 21

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.login_controller = None
        self.upload_controller = None
        self.feed_controller = None

        # 登录方式: qr (二维码) / sms (短信) / password (密码)
        self.login_method = self.config.get("login_method", "qr")
        self.username = self.config.get("username", "")
        self.password = self.config.get("password", "")

        # 默认投稿参数
        self.default_copyright = self.config.get("copyright", 1)  # 1=原创, 2=转载
        self.default_tid = self.config.get("tid", self.DEFAULT_TID)
        self.default_tags = self.config.get("default_tags", ["bilitool"])

        self._init_controllers()

    @property
    def platform_name(self) -> str:
        return "B站"

    def _init_controllers(self):
        """初始化 bilitool 控制器。"""
        try:
            from bilitool import (
                FeedController,
                LoginController,
                UploadController,
            )
            self.login_controller = LoginController()
            self.upload_controller = UploadController()
            self.feed_controller = FeedController()
            logger.info("[B站] bilitool 控制器初始化完成")
        except ImportError:
            logger.error("[B站] 未安装 bilitool，请运行: pip install bilitool")
            raise

    async def login(self, **kwargs) -> bool:
        """
        登录B站。

        支持方式:
        - qr: 二维码登录（默认，推荐）
        - sms: 短信验证码登录
        - password: 账号密码登录
        """
        if not self.login_controller:
            return False

        try:
            # 先检查是否已登录
            check = self.login_controller.check_bilibili_login()
            if check:
                logger.info("[B站] 已登录")
                self._is_logged_in = True
                return True

            logger.info("[B站] 使用 %s 方式登录...", self.login_method)

            if self.login_method == "qr":
                # 二维码登录
                logger.info("[B站] 请扫描弹出的二维码...")
                self.login_controller.login_bilibili(export=True)
            elif self.login_method == "password" and self.username and self.password:
                # 账号密码登录
                logger.info("[B站] 使用账号密码登录...")
                self.login_controller.login_bilibili(
                    username=self.username,
                    password=self.password,
                )
            else:
                # 默认二维码登录
                logger.info("[B站] 请扫描弹出的二维码...")
                self.login_controller.login_bilibili(export=True)

            # 检查登录结果
            check = self.login_controller.check_bilibili_login()
            self._is_logged_in = check

            if check:
                logger.info("[B站] 登录成功!")
            else:
                logger.error("[B站] 登录失败")

            return check

        except Exception as e:
            logger.error("[B站] 登录异常: %s", e)
            return False

    async def check_login_status(self) -> bool:
        """检查登录状态。"""
        if not self.login_controller:
            return False

        try:
            is_login = self.login_controller.check_bilibili_login()
            self._is_logged_in = is_login
            return is_login
        except Exception as e:
            logger.error("[B站] 检查登录状态失败: %s", e)
            return False

    async def publish(self, content: ContentItem) -> PublishResult:
        """
        发布视频到B站。

        使用 bilitool 的 upload_video_entry 方法。
        """
        if not await self.check_login_status():
            if not await self.login():
                return self._create_failure_result("登录失败，无法发布")

        if not content.video_path:
            return self._create_failure_result("B站投稿需要视频文件，请提供video_path")

        if not os.path.exists(content.video_path):
            return self._create_failure_result(f"视频文件不存在: {content.video_path}")

        try:
            # 准备投稿参数
            title = content.get_platform_title(PlatformType.BILIBILI)
            desc = content.get_platform_content(PlatformType.BILIBILI)
            tags = content.get_platform_tags(PlatformType.BILIBILI)

            # 合并标签
            if not tags:
                tags = self.default_tags
            tag_str = ",".join(tags[:10])  # B站最多10个标签

            # 确定分区
            tid = self.default_tid
            extra = content.platform_extra.get(PlatformType.BILIBILI, {})
            if "tid" in extra:
                tid = extra["tid"]
            elif "category" in extra:
                category = extra["category"]
                tid = self.TID_MAPPING.get(category, self.DEFAULT_TID)

            # 封面
            cover = content.cover_path or ""

            # 动态
            dynamic = extra.get("dynamic", "")

            # 版权
            copyright = extra.get("copyright", self.default_copyright)
            source = extra.get("source", "来源于网络") if copyright == 2 else ""

            logger.info("[B站] 开始投稿: %s", title)
            logger.info("[B站] 分区: %s, 标签: %s", tid, tag_str)

            # 调用 bilitool 上传
            # upload_video_entry 参数:
            # video_path, yaml, copyright, tid, title, desc, tag, source, cover, dynamic, cdn
            result = self.upload_controller.upload_video_entry(
                video_path=content.video_path,
                yaml="",  # 不使用yaml配置
                copyright=copyright,
                tid=tid,
                title=title,
                desc=desc,
                tag=tag_str,
                source=source,
                cover=cover,
                dynamic=dynamic,
                cdn="",  # 自动选择最佳CDN
            )

            # 解析结果
            # bilitool 返回的是日志输出，需要通过list查询确认
            logger.info("[B站] 视频上传完成，查询投稿状态...")
            await asyncio.sleep(3)

            # 查询最新投稿获取bvid
            video_list = self.feed_controller.print_video_list_info(size=5, status="published")

            # 尝试从结果中解析BV号
            bvid = None
            if hasattr(result, "get") and result.get("bvid"):
                bvid = result.get("bvid")

            video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else None

            return self._create_success_result(
                message="视频投稿成功，正在审核中",
                url=video_url,
                content_id=bvid,
                raw_response={"bvid": bvid} if bvid else {}
            )

        except Exception as e:
            logger.exception("[B站] 投稿异常")
            return self._create_failure_result(f"投稿异常: {e}")

    async def publish_with_yaml(self, content: ContentItem, yaml_path: str) -> PublishResult:
        """
        使用YAML配置文件投稿（高级用法）。

        Args:
            content: 内容模型
            yaml_path: YAML配置文件路径
        """
        if not await self.check_login_status():
            if not await self.login():
                return self._create_failure_result("登录失败")

        try:
            result = self.upload_controller.upload_video_entry(
                video_path=content.video_path,
                yaml=yaml_path,
            )

            return self._create_success_result(
                message="YAML配置投稿成功",
                raw_response=result
            )

        except Exception as e:
            return self._create_failure_result(f"YAML投稿失败: {e}")

    async def append_video(self, video_path: str, bvid: str) -> PublishResult:
        """
        追加视频到已有投稿（分P）。

        Args:
            video_path: 视频文件路径
            bvid: 目标BV号
        """
        if not await self.check_login_status():
            if not await self.login():
                return self._create_failure_result("登录失败")

        try:
            self.upload_controller.append_video_entry(
                video_path=video_path,
                bvid=bvid,
                cdn=""
            )

            return self._create_success_result(
                message=f"分P追加成功: {bvid}",
                content_id=bvid
            )

        except Exception as e:
            return self._create_failure_result(f"分P追加失败: {e}")

    async def get_video_list(self, size: int = 20, status: str = "is_pubing"):
        """获取投稿视频列表。"""
        try:
            return self.feed_controller.print_video_list_info(
                size=size,
                status=status
            )
        except Exception as e:
            logger.error("[B站] 获取视频列表失败: %s", e)
            return None

    async def cleanup(self):
        """清理资源。"""
        try:
            # bilitool 无需显式清理
            logger.info("[B站] 资源已清理")
        except Exception as e:
            logger.error("[B站] 资源清理失败: %s", e)
