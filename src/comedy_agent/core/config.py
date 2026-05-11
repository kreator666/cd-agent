"""全局配置管理。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# 加载 .env 文件
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(ENV_PATH, override=True)


class Settings(BaseSettings):
    """应用配置。"""

    # 项目路径
    project_root: Path = Field(default=Path(__file__).resolve().parents[2])
    data_dir: Path = Field(default=Path(__file__).resolve().parents[3] / "data")
    skills_dir: Path = Field(default=Path(__file__).resolve().parents[3] / "skills")

    # LLM API Keys
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    qwen_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    moonshot_api_key: str = Field(default="", alias="MOONSHOT_API_KEY")

    # 默认模型
    default_model: str = Field(default="gpt-4o", alias="DEFAULT_MODEL")
    default_embedding_model: str = Field(
        default="text-embedding-3-large", alias="DEFAULT_EMBEDDING_MODEL"
    )

    # 向量数据库
    vector_db_path: str = Field(default="./chroma_data", alias="VECTOR_DB_PATH")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # LangSmith 可观测性
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="comedy-agent", alias="LANGSMITH_PROJECT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局单例
settings = Settings()
