# Comedy Agent 云端部署指南

## 一、虚拟机配置建议

### 方案 A：纯云端 API 模式（推荐）

所有 LLM 调用均通过外部 API（OpenAI / Claude / 通义千问 / Kimi 等），无需本地 GPU。

| 配置项 | 最低配置 | 推荐配置 |
|--------|---------|---------|
| CPU | 2 vCPU | 4 vCPU |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 50 GB SSD | 50 GB SSD |
| GPU | 无需 | 无需 |
| 带宽 | 5 Mbps | 10 Mbps |
| 操作系统 | Ubuntu 22.04/24.04 LTS | Ubuntu 24.04 LTS |

**适用场景**：
- 团队内部使用
- 对数据隐私要求不高
- 追求部署简单、成本可控

**月成本估算**（主流云厂商）：
- 阿里云 ECS `ecs.c7.large`（2C4G）：约 ¥200-300/月
- 腾讯云 CVM `S5.2XLARGE8`（4C8G）：约 ¥400-500/月
- AWS `t3.xlarge`（4C16G）：约 $120-150/月

---

### 方案 B：本地 Ollama 模型模式

在服务器本地运行 Ollama 服务，使用开源模型（如 llama3.1、qwen2.5），无需 API Key，数据完全本地。

| 配置项 | 最低配置 | 推荐配置 |
|--------|---------|---------|
| CPU | 4 vCPU | 8 vCPU |
| 内存 | 16 GB | 32 GB |
| 磁盘 | 100 GB SSD | 200 GB SSD |
| GPU | NVIDIA T4 16GB | NVIDIA A10 24GB / L4 24GB |
| 带宽 | 5 Mbps | 10 Mbps |
| 操作系统 | Ubuntu 22.04/24.04 LTS | Ubuntu 24.04 LTS |

**适用场景**：
- 数据敏感，要求完全离线
- 已有 GPU 机器或愿意承担 GPU 成本
- 高频调用，API 成本过高

**月成本估算**（主流云厂商）：
- 阿里云 GPU `gn7i-c8g1.2xlarge`（V100 16G）：约 ¥2,500-3,500/月
- 阿里云 GPU `gn7i-c16g1.4xlarge`（T4 16G）：约 ¥3,500-4,500/月
- 腾讯云 GPU `GN7`（T4 16G）：约 ¥3,000-4,000/月

> **注意**：Ollama 在纯 CPU 模式下也可以运行，但 7B 模型推理速度极慢（数分钟/请求），不建议生产使用。

---

## 二、服务依赖清单

### 核心依赖（必须）

| 服务 | 类型 | 用途 | 版本 |
|------|------|------|------|
| Python | 运行时 | 应用运行环境 | ≥ 3.11 |
| Redis | 基础设施 | 缓存、限流、短期记忆 | 7.x |
| ChromaDB | 嵌入式库 | 向量数据库存储 | ≥ 0.5.0 |
| SQLite | 嵌入式库 | 用户记忆、偏好、作品 | 随系统 |
| FastAPI/Uvicorn | 应用框架 | HTTP API 服务 | 随项目依赖 |

### 可选依赖

| 服务 | 类型 | 用途 | 说明 |
|------|------|------|------|
| Nginx | 反向代理 | HTTPS、域名绑定、静态文件 | 裸机部署时推荐 |
| Ollama | 本地模型 | 离线 LLM 推理 | 方案 B 必需 |
| Docker + Docker Compose | 容器化 | 一键部署所有服务 | 推荐 |

### 外部 API（按需配置）

| 提供商 | 用途 | 环境变量 |
|--------|------|---------|
| OpenAI | GPT-4o / GPT-4o-mini | `OPENAI_API_KEY` |
| Anthropic | Claude 3.5 Sonnet / Opus | `ANTHROPIC_API_KEY` |
| 阿里云 | 通义千问 qwen-max / qwen-turbo | `DASHSCOPE_API_KEY` |
| Moonshot | Kimi 系列模型 | `MOONSHOT_API_KEY` |
| LangSmith | 调用链路追踪与监控 | `LANGSMITH_API_KEY` |

---

## 三、端口规划

| 端口 | 服务 | 说明 |
|------|------|------|
| 8000 | Comedy Agent API | 主应用入口 |
| 6379 | Redis | 缓存与限流（建议不暴露到公网）|
| 80 / 443 | Nginx | HTTP / HTTPS（如有域名）|
| 11434 | Ollama | 本地模型 API（可选）|

---

## 四、快速部署

### 方式一：Docker Compose（推荐，5 分钟完成）

```bash
# 1. 克隆代码到服务器
git clone <你的仓库地址> /opt/comedy-agent
cd /opt/comedy-agent

# 2. 填写环境变量
cp .env.example .env
nano .env   # 填入至少一个 API Key

# 3. 一键启动
bash deploy/install-docker.sh
```

### 方式二：裸机部署（适合已有 Python 环境）

```bash
# 1. 克隆代码
git clone <你的仓库地址> /opt/comedy-agent
cd /opt/comedy-agent

# 2. 一键安装与启动
bash deploy/install-native.sh
```

---

## 五、生产环境建议

1. **HTTPS**：使用 Nginx + Let's Encrypt 或云厂商负载均衡证书
2. **备份**：定期备份 `./data` 和 `./chroma_data` 目录
3. **监控**：配置 LangSmith 追踪，或使用云厂商基础监控
4. **安全**：Redis 不暴露公网，API Key 通过环境变量注入
5. **日志**：使用 `docker compose logs -f api` 查看实时日志，或配置日志轮转
