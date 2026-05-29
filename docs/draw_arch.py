"""用 matplotlib 绘制 Comedy Agent 架构图。"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(1, 1, figsize=(22, 16))
ax.set_xlim(0, 22)
ax.set_ylim(0, 16)
ax.axis('off')

# 颜色定义
colors = {
    'user': '#E3F2FD',
    'frontend': '#E0F7FA',
    'api': '#E8F5E9',
    'agent': '#FFF8E1',
    'skill_done': '#D4EDDA',
    'skill_todo': '#F8D7DA',
    'infra': '#F3E5F5',
    'config': '#FFF3E0',
    'rag': '#E8EAF6',
    'memory': '#FCE4EC',
    'border_user': '#2196F3',
    'border_frontend': '#00BCD4',
    'border_api': '#4CAF50',
    'border_agent': '#FF9800',
    'border_skill_done': '#28A745',
    'border_skill_todo': '#DC3545',
    'border_infra': '#9C27B0',
    'border_config': '#FF9800',
    'border_rag': '#3F51B5',
    'border_memory': '#E91E63',
}

def draw_box(ax, x, y, w, h, text, facecolor, edgecolor, linestyle='-', fontsize=8, bold=False):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.15",
                         facecolor=facecolor, edgecolor=edgecolor, linewidth=1.8, linestyle=linestyle)
    ax.add_patch(box)
    weight = 'bold' if bold else 'normal'
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=fontsize,
            weight=weight, wrap=True)
    return box

def draw_arrow(ax, x1, y1, x2, y2, color='#555'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.3))

def draw_dashed_arrow(ax, x1, y1, x2, y2, color='#777'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.1, linestyle='--'))

# 标题
ax.text(11, 15.5, 'Comedy Agent 系统架构图', ha='center', va='center', fontsize=22, weight='bold', color='#2C3E50')
ax.text(11, 15.0, '阶段：第五阶段 工程化与优化（进行中）· 402 个测试用例全部通过',
        ha='center', va='center', fontsize=10, color='#555')

# ========== 用户层 ==========
ax.text(0.5, 14.3, '用户层', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 0.5, 13.3, 2.6, 0.9, '命令行终端', colors['user'], colors['border_user'], fontsize=10)
draw_box(ax, 3.5, 13.3, 3.0, 0.9, '浏览器 / HTTP 客户端', colors['user'], colors['border_user'], fontsize=10)

# ========== 前端层 ==========
ax.text(7.0, 14.3, '前端层 (frontend/)', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 7.0, 13.3, 2.4, 0.9, 'index.html\n创作聊天', colors['frontend'], colors['border_frontend'], fontsize=8)
draw_box(ax, 9.6, 13.3, 2.4, 0.9, 'skills.html\nSkill 管理', colors['frontend'], colors['border_frontend'], fontsize=8)
draw_box(ax, 12.2, 13.3, 2.4, 0.9, 'knowledge.html\n知识库', colors['frontend'], colors['border_frontend'], fontsize=8)
draw_box(ax, 14.8, 13.3, 2.4, 0.9, 'me.html\n个人中心', colors['frontend'], colors['border_frontend'], fontsize=8)

# ========== API 接入层 ==========
ax.text(0.5, 12.5, 'API 接入层 (api/)', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 0.5, 11.3, 3.2, 1.0, 'CLI\ncomedy-agent chat/run/skill\n(api/cli.py)', colors['api'], colors['border_api'], fontsize=8)
draw_box(ax, 4.2, 11.3, 3.6, 1.0, 'HTTP API\nFastAPI / Uvicorn\n(api/server.py)', colors['api'], colors['border_api'], fontsize=8, bold=True)

# ========== Agent 核心层 ==========
ax.text(0.5, 10.5, 'Agent 核心层 (agent/)', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 0.5, 9.1, 7.8, 1.2, 'AgentOrchestrator\nLangChain create_agent · 路由 & 调度 + RAG + 记忆注入\n(agent/orchestrator.py)',
         colors['agent'], colors['border_agent'], fontsize=9, bold=True)

# ========== Skill 技能层 ==========
ax.text(0.5, 8.5, 'Skill 技能层 (skills/)', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 0.5, 7.0, 2.4, 1.2, 'ComedySkill 基类\nBaseTool + RAG 检索\n(skills/base.py)', colors['skill_done'], colors['border_skill_done'], fontsize=8, bold=True)
draw_box(ax, 3.2, 7.0, 1.8, 1.2, 'StandupSkill\n脱口秀', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 5.3, 7.0, 1.8, 1.2, 'CrosstalkSkill\n相声', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 7.4, 7.0, 1.8, 1.2, 'SketchSkill\n小品', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 0.5, 5.5, 1.8, 1.2, 'SitcomSkill\n情景喜剧', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 2.6, 5.5, 1.8, 1.2, 'ManzaiSkill\n漫才', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 4.7, 5.5, 1.8, 1.2, 'Japanese\nSketchSkill\n日式短剧', colors['skill_done'], colors['border_skill_done'], fontsize=7)
draw_box(ax, 6.8, 5.5, 1.8, 1.2, 'JokeAnalyzer\n笑点分析', colors['skill_done'], colors['border_skill_done'], fontsize=8)

# ========== 基础设施层 ==========
ax.text(9.0, 12.5, '基础设施层', fontsize=11, weight='bold', color='#34495E')

# 模型层
ax.text(9.0, 12.0, '模型层 (models/)', fontsize=10, weight='bold', color='#7B1FA2')
draw_box(ax, 9.0, 10.6, 3.0, 1.2, 'ModelFactory\n统一模型工厂\n(models/factory.py)', colors['infra'], colors['border_infra'], fontsize=9, bold=True)
draw_box(ax, 12.3, 11.1, 1.6, 0.7, 'OpenAI\nGPT-4o', colors['infra'], colors['border_infra'], fontsize=7)
draw_box(ax, 14.1, 11.1, 1.6, 0.7, 'Anthropic\nClaude 3.5', colors['infra'], colors['border_infra'], fontsize=7)
draw_box(ax, 15.9, 11.1, 1.6, 0.7, '通义千问\nqwen-max', colors['infra'], colors['border_infra'], fontsize=7)
draw_box(ax, 12.3, 10.3, 1.6, 0.7, 'Ollama\nLlama3.1', colors['infra'], colors['border_infra'], fontsize=7)
draw_box(ax, 14.1, 10.3, 1.6, 0.7, 'Moonshot\nKimi', colors['infra'], colors['border_infra'], fontsize=7)
draw_box(ax, 15.9, 10.3, 1.6, 0.7, 'HuggingFace\nall-MiniLM-L6-v2', colors['infra'], colors['border_infra'], fontsize=7)

# RAG 知识库
ax.text(9.0, 9.6, 'RAG 知识库 (rag/)', fontsize=10, weight='bold', color='#3F51B5')
draw_box(ax, 9.0, 8.2, 2.8, 1.2, 'ComedyRetriever\n混合检索\n(rag/retriever.py)', colors['rag'], colors['border_rag'], fontsize=8)
draw_box(ax, 12.1, 8.2, 2.4, 1.2, 'VectorStore\nChromaDB\n(rag/vector_store.py)', colors['rag'], colors['border_rag'], fontsize=8)
draw_box(ax, 14.8, 8.2, 2.8, 1.2, 'KnowledgeIngestor\n文档解析 & 分块\n(rag/ingest.py)', colors['rag'], colors['border_rag'], fontsize=8)
draw_box(ax, 9.0, 6.8, 2.6, 1.0, '个人知识库\nuser_knowledge_{uid}', colors['rag'], colors['border_rag'], fontsize=8)
draw_box(ax, 11.9, 6.8, 2.6, 1.0, '默认知识库\ncomedy_knowledge', colors['rag'], colors['border_rag'], fontsize=8)

# 记忆系统
ax.text(15.0, 9.6, '记忆系统 (memory/)', fontsize=10, weight='bold', color='#E91E63')
draw_box(ax, 15.0, 8.2, 2.6, 1.2, 'UnifiedMemory\n统一记忆接口\n(memory/unified.py)', colors['memory'], colors['border_memory'], fontsize=8)
draw_box(ax, 17.9, 8.2, 2.4, 1.2, 'SQLModel Schema\nUserProfile / Preference /\nConversation / Script', colors['memory'], colors['border_memory'], fontsize=7)
draw_box(ax, 15.0, 6.8, 2.6, 1.0, 'PreferenceExtractor\n偏好自动提取', colors['memory'], colors['border_memory'], fontsize=8)
draw_box(ax, 17.9, 6.8, 2.4, 1.0, 'SQLite / PostgreSQL\n+ Redis 缓存', colors['memory'], colors['border_memory'], fontsize=8)

# 配置中心
ax.text(9.0, 6.2, '配置中心 (core/)', fontsize=10, weight='bold', color='#FF9800')
draw_box(ax, 9.0, 4.8, 2.8, 1.2, 'Settings\nPydantic BaseSettings\n(core/config.py)', colors['config'], colors['border_config'], fontsize=8)
draw_box(ax, 12.1, 4.8, 2.8, 1.2, 'PromptManager\n外部模板热加载\n(core/prompt_manager.py)', colors['config'], colors['border_config'], fontsize=8)
draw_box(ax, 15.2, 5.1, 1.8, 0.8, '.env\n环境变量', colors['config'], colors['border_config'], fontsize=8)

# ========== 连接箭头 ==========
# 用户 -> 前端 / API
draw_arrow(ax, 1.8, 13.3, 2.1, 12.3)
draw_arrow(ax, 5.0, 13.3, 5.2, 12.3)
draw_arrow(ax, 8.2, 13.3, 6.0, 12.3)

# API -> Agent
draw_arrow(ax, 2.1, 11.3, 2.5, 10.3)
draw_arrow(ax, 6.0, 11.3, 5.4, 10.3)

# Agent -> Skill
draw_arrow(ax, 3.5, 9.1, 1.7, 8.2)
draw_arrow(ax, 3.5, 9.1, 4.1, 8.2)
draw_arrow(ax, 3.5, 9.1, 6.2, 8.2)
draw_arrow(ax, 3.5, 9.1, 8.3, 8.2)
draw_arrow(ax, 3.5, 9.1, 1.4, 6.7)
draw_arrow(ax, 3.5, 9.1, 3.5, 6.7)
draw_arrow(ax, 3.5, 9.1, 5.6, 6.7)
draw_arrow(ax, 3.5, 9.1, 7.7, 6.7)

# Agent -> ModelFactory
draw_arrow(ax, 8.3, 9.7, 9.0, 10.0)

# Skill -> ModelFactory
draw_arrow(ax, 5.5, 7.0, 8.5, 7.2, color='#777')

# ModelFactory -> 各模型
draw_arrow(ax, 12.0, 11.1, 12.3, 11.1)
draw_arrow(ax, 12.0, 10.8, 12.3, 10.7)
draw_arrow(ax, 12.0, 10.5, 12.3, 10.3)
draw_arrow(ax, 12.0, 10.2, 12.3, 9.5)
draw_arrow(ax, 13.8, 10.3, 14.1, 10.3)
draw_arrow(ax, 15.6, 10.3, 15.9, 10.3)

# ModelFactory -> Embedding
draw_arrow(ax, 12.0, 10.0, 15.9, 10.5)

# ModelFactory -> Settings
draw_arrow(ax, 11.0, 10.6, 11.0, 6.0)

# Settings -> .env / PromptMgr
draw_arrow(ax, 11.8, 5.4, 12.1, 5.4)
draw_arrow(ax, 11.8, 5.1, 15.2, 5.5)

# Agent -> RAG / Memory
draw_dashed_arrow(ax, 8.3, 9.1, 10.4, 9.4)
draw_dashed_arrow(ax, 8.3, 8.8, 16.3, 9.4)

# RAG 内部
draw_arrow(ax, 11.8, 8.2, 12.1, 8.8)
draw_arrow(ax, 14.5, 8.2, 14.8, 8.8)
draw_arrow(ax, 13.3, 8.2, 13.2, 7.8)
draw_arrow(ax, 10.3, 6.8, 10.3, 6.4, color='#3F51B5')
draw_arrow(ax, 13.2, 6.8, 13.2, 6.4, color='#3F51B5')

# Memory 内部
draw_arrow(ax, 17.5, 8.2, 17.9, 8.8)
draw_arrow(ax, 16.3, 6.8, 16.3, 6.4, color='#E91E63')
draw_arrow(ax, 19.1, 6.8, 19.1, 6.4, color='#E91E63')

# Ingestor -> VectorStore
draw_arrow(ax, 16.2, 8.2, 14.5, 8.2)

# ========== 图例 ==========
legend_x = 0.5
legend_y = 3.2
ax.text(legend_x, legend_y + 0.8, '图例', fontsize=11, weight='bold', color='#2C3E50')
draw_box(ax, legend_x, legend_y, 1.4, 0.5, '已实现', colors['skill_done'], colors['border_skill_done'], fontsize=9)
draw_box(ax, legend_x + 1.8, legend_y, 1.4, 0.5, '进行中', '#FFF3CD', '#FFC107', fontsize=9)
draw_box(ax, legend_x + 3.6, legend_y, 1.4, 0.5, '前端', colors['frontend'], colors['border_frontend'], fontsize=9)

# 阶段说明
ax.text(0.5, 2.3, '第三阶段 [完成] RAG 知识库建设 · 第四阶段 [完成] 记忆系统与用户层 · 第五阶段 [进行中] 工程化与优化',
        fontsize=10, weight='bold', color='#28A745')
ax.text(0.5, 1.7, '核心能力：Agent 决策层 + Skill 创作层 均支持 RAG 知识库注入 · 个人知识库 + 默认知识库联合检索',
        fontsize=9, color='#555')
ax.text(0.5, 1.2, '内置 Skill：8 个（6 创作 + 2 分析）· 测试：402 个用例全部通过 · 前端：8 个独立页面',
        fontsize=9, color='#555')

plt.tight_layout()
plt.savefig('docs/architecture.png', dpi=200, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.close()
print('架构图已保存至 docs/architecture.png')
