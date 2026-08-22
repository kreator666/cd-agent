"""全局配置管理。"""

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
    prompts_dir: Path = Field(default=Path(__file__).resolve().parents[3] / "data" / "prompts")

    # LLM API Keys
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    qwen_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    moonshot_api_key: str = Field(default="", alias="MOONSHOT_API_KEY")
    wj_api_key: str = Field(default="", alias="WJ_API_KEY")
    wj_base_url: str = Field(
        default="https://maas-openapi.wanjiedata.com/api/v1", alias="WJ_BASE_URL"
    )

    # 素材搜索：RSS 新闻源列表（逗号分隔）
    news_rss_feeds: str = Field(
        default=(
            "https://www.chinanews.com.cn/rss/scroll-news.xml,"
            "https://www.chinanews.com.cn/rss/china.xml,"
            "https://www.chinanews.com.cn/rss/world.xml,"
            "https://www.chinanews.com.cn/rss/finance.xml,"
            "https://www.ithome.com/rss/,"
            "https://36kr.com/feed,"
            "https://rss.mifaw.com/articles/5c8bb11a3c41f61efd36683e/5c919d543882afa09dff3fa3"
        ),
        alias="NEWS_RSS_FEEDS",
    )

    # 默认模型
    default_model: str = Field(default="deepseek-v4-flash", alias="DEFAULT_MODEL")
    default_embedding_model: str = Field(
        default="text-embedding-3-large", alias="DEFAULT_EMBEDDING_MODEL"
    )


    # 向量数据库
    vector_db_path: str = Field(default="./chroma_data", alias="VECTOR_DB_PATH")

    # 记忆数据库（SQLite）
    memory_db_path: str = Field(default="./data/memory.db", alias="MEMORY_DB_PATH")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # 缓存与限流
    cache_ttl: int = Field(default=300, alias="CACHE_TTL")
    rate_limit_write_max: int = Field(default=60, alias="RATE_LIMIT_WRITE_MAX")
    rate_limit_write_window: int = Field(default=60, alias="RATE_LIMIT_WRITE_WINDOW")
    rate_limit_read_max: int = Field(default=120, alias="RATE_LIMIT_READ_MAX")
    rate_limit_read_window: int = Field(default=60, alias="RATE_LIMIT_READ_WINDOW")

    # 模型分层配置（任务类型绑定模型）
    creative_model: str = Field(default="deepseek-v4-flash", alias="CREATIVE_MODEL")
    analytical_model: str = Field(default="deepseek-v4-flash", alias="ANALYTICAL_MODEL")
    fast_model: str = Field(default="gpt-4o-mini", alias="FAST_MODEL")

    # Fallback 备用模型链（逗号分隔）
    creative_fallback_models: str = Field(default="gpt-4o,qwen-max", alias="CREATIVE_FALLBACK_MODELS")
    analytical_fallback_models: str = Field(default="qwen-max,gpt-4o-mini", alias="ANALYTICAL_FALLBACK_MODELS")
    fast_fallback_models: str = Field(default="qwen-turbo,ollama-qwen2.5", alias="FAST_FALLBACK_MODELS")

    # LangSmith 可观测性
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="comedy-agent", alias="LANGSMITH_PROJECT")

    # Anyway Business 支付
    anyway_merchant_api_key: str = Field(default="", alias="ANYWAY_MERCHANT_API_KEY")
    anyway_payment_link_url: str = Field(default="", alias="ANYWAY_PAYMENT_LINK_URL")
    anyway_webhook_signing_key: str = Field(default="", alias="ANYWAY_WEBHOOK_SIGNING_KEY")
    anyway_webhook_path: str = Field(default="/webhooks/anyway", alias="ANYWAY_WEBHOOK_PATH")
    anyway_fee_percent: float = Field(default=5.0, ge=0.0, le=100.0, alias="ANYWAY_FEE_PERCENT")
    anyway_min_tip_cents: int = Field(default=100, alias="ANYWAY_MIN_TIP_CENTS")
    anyway_max_tip_cents: int = Field(default=1000000, alias="ANYWAY_MAX_TIP_CENTS")

    # 管理员账号（仅支持单一硬编码管理员，密码从环境变量读取）
    admin_user_id: str = Field(default="admin", alias="ADMIN_USER_ID")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")

    # 加密货币打赏（Base 链校验）
    base_rpc_url: str = Field(default="https://mainnet.base.org", alias="BASE_RPC_URL")
    tip_token_contract: str = Field(default="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", alias="TIP_TOKEN_CONTRACT")
    tip_token_decimals: int = Field(default=6, alias="TIP_TOKEN_DECIMALS")
    tip_chain_confirmations: int = Field(default=12, alias="TIP_CHAIN_CONFIRMATIONS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局单例
settings = Settings()
