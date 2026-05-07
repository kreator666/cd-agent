"""记忆存储 —— 用户偏好、历史对话、创作习惯的读写接口。

预留接口，将在任务 4.x 中实现。
"""


class MemoryStore:
    """记忆存储。"""

    def save(self, user_id: str, key: str, value: str) -> None:
        """保存用户记忆。"""
        raise NotImplementedError("将在第四阶段实现。")

    def load(self, user_id: str, key: str) -> str | None:
        """读取用户记忆。"""
        raise NotImplementedError("将在第四阶段实现。")
