"""用 matplotlib 绘制 Comedy Agent 架构图。"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(1, 1, figsize=(18, 14))
ax.set_xlim(0, 18)
ax.set_ylim(0, 14)
ax.axis('off')

# 颜色定义
colors = {
    'user': '#E3F2FD',
    'api': '#E8F5E9',
    'agent': '#FFF8E1',
    'skill_done': '#D4EDDA',
    'skill_todo': '#F8D7DA',
    'infra': '#F3E5F5',
    'config': '#FFF3E0',
    'border_user': '#2196F3',
    'border_api': '#4CAF50',
    'border_agent': '#FF9800',
    'border_skill_done': '#28A745',
    'border_skill_todo': '#DC3545',
    'border_infra': '#9C27B0',
    'border_config': '#FF9800',
}

def draw_box(ax, x, y, w, h, text, facecolor, edgecolor, linestyle='-', fontsize=9, bold=False):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.2",
                         facecolor=facecolor, edgecolor=edgecolor, linewidth=2, linestyle=linestyle)
    ax.add_patch(box)
    weight = 'bold' if bold else 'normal'
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=fontsize,
            weight=weight, wrap=True)
    return box

def draw_arrow(ax, x1, y1, x2, y2, color='#555'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

def draw_dashed_arrow(ax, x1, y1, x2, y2, color='#999'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2, linestyle='--'))

# 标题
ax.text(9, 13.5, 'Comedy Agent 系统架构图', ha='center', va='center', fontsize=20, weight='bold', color='#2C3E50')

# ========== 用户层 ==========
draw_box(ax, 2, 11.8, 2.8, 1.0, '命令行终端', colors['user'], colors['border_user'], fontsize=10)
draw_box(ax, 6, 11.8, 3.2, 1.0, 'HTTP 客户端 / 前端', colors['user'], colors['border_user'], fontsize=10)

# ========== API 接入层 ==========
ax.text(1.2, 11.3, 'API 接入层', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 2, 9.8, 3.0, 1.2, 'CLI\ncomedy-agent chat/run/skill\n(api/cli.py)', colors['api'], colors['border_api'], fontsize=9)
draw_box(ax, 6, 9.8, 3.4, 1.2, 'HTTP API\nFastAPI / Uvicorn\n(api/server.py)', colors['api'], colors['border_api'], fontsize=9)

# ========== Agent 核心层 ==========
ax.text(1.2, 9.3, 'Agent 核心层', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 3.5, 7.8, 4.4, 1.2, 'AgentOrchestrator\nLangChain create_agent · 路由 & 调度\n(agent/orchestrator.py)', colors['agent'], colors['border_agent'], fontsize=9, bold=True)

# ========== Skill 技能层 ==========
ax.text(1.2, 7.3, 'Skill 技能层', fontsize=11, weight='bold', color='#34495E')
draw_box(ax, 0.8, 5.5, 2.6, 1.2, 'ComedySkill 基类\nBaseTool + ABC\n(skills/base.py)', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 4.0, 5.5, 2.6, 1.2, 'StandupSkill [DONE]\n脱口秀创作\n(skills/standup.py)', colors['skill_done'], colors['border_skill_done'], fontsize=8)
draw_box(ax, 7.2, 5.5, 2.0, 1.2, '相声创作\n(预留)', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=8)
draw_box(ax, 9.6, 5.5, 2.0, 1.2, '小品创作\n(预留)', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=8)
draw_box(ax, 12.0, 5.5, 2.0, 1.2, '笑点分析\n(预留)', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=8)

# ========== 基础设施层 ==========
ax.text(9.2, 11.3, '基础设施层', fontsize=11, weight='bold', color='#34495E')

# 模型层
ax.text(9.2, 10.8, '模型层 (models/)', fontsize=10, weight='bold', color='#7B1FA2')
draw_box(ax, 9.2, 9.4, 3.2, 1.2, 'ModelFactory\n统一模型工厂\n(models/factory.py)', colors['infra'], colors['border_infra'], fontsize=9, bold=True)
draw_box(ax, 12.8, 9.8, 1.8, 0.7, 'OpenAI\nGPT-4o', colors['infra'], colors['border_infra'], fontsize=8)
draw_box(ax, 14.8, 9.8, 1.8, 0.7, 'Anthropic\nClaude 3.5', colors['infra'], colors['border_infra'], fontsize=8)
draw_box(ax, 12.8, 9.0, 1.8, 0.7, 'Ollama\nLlama3', colors['infra'], colors['border_infra'], fontsize=8)
draw_box(ax, 14.8, 9.0, 1.8, 0.7, '通义千问\nqwen-max', colors['infra'], colors['border_infra'], fontsize=8)
draw_box(ax, 13.8, 8.2, 1.8, 0.7, 'Moonshot / Kimi', colors['infra'], colors['border_infra'], fontsize=8)

# RAG
ax.text(9.2, 7.9, 'RAG 知识库 (rag/)', fontsize=10, weight='bold', color='#7B1FA2')
draw_box(ax, 9.2, 6.5, 3.2, 1.2, 'ComedyRetriever\n混合检索\n(rag/retriever.py)\n[第三阶段实现]', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=9)

# 记忆
ax.text(13.0, 7.9, '记忆系统 (memory/)', fontsize=10, weight='bold', color='#7B1FA2')
draw_box(ax, 13.0, 6.5, 3.2, 1.2, 'MemoryStore\n用户偏好 & 历史\n(memory/store.py)\n[第四阶段实现]', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=9)

# 配置中心
ax.text(9.2, 5.9, '配置中心 (core/)', fontsize=10, weight='bold', color='#7B1FA2')
draw_box(ax, 9.2, 4.5, 3.2, 1.2, 'Settings\nPydantic BaseSettings\n(core/config.py)', colors['config'], colors['border_config'], fontsize=9)
draw_box(ax, 13.0, 4.8, 2.4, 0.8, '.env\n环境变量', colors['config'], colors['border_config'], fontsize=9)

# ========== 连接箭头 ==========
# 用户 -> API
draw_arrow(ax, 3.4, 11.8, 3.5, 11.0)
draw_arrow(ax, 7.6, 11.8, 7.7, 11.0)

# API -> Agent
draw_arrow(ax, 3.5, 9.8, 4.5, 9.0)
draw_arrow(ax, 7.7, 9.8, 6.9, 9.0)

# Agent -> Skill
draw_arrow(ax, 5.7, 7.8, 2.1, 6.7)
draw_arrow(ax, 5.7, 7.8, 5.3, 6.7)
draw_arrow(ax, 5.7, 7.8, 8.2, 6.7)
draw_arrow(ax, 5.7, 7.8, 10.6, 6.7)
draw_arrow(ax, 5.7, 7.8, 13.0, 6.7)

# Agent -> ModelFactory
draw_arrow(ax, 7.9, 8.4, 9.2, 8.9)

# Skill -> ModelFactory
draw_arrow(ax, 5.3, 5.5, 8.5, 5.3, color='#777')
draw_arrow(ax, 5.3, 5.5, 8.0, 5.2, color='#777')

# ModelFactory -> 各模型
draw_arrow(ax, 12.4, 9.8, 12.8, 9.8)
draw_arrow(ax, 12.4, 9.6, 12.8, 9.4)
draw_arrow(ax, 12.4, 9.4, 12.8, 9.0)
draw_arrow(ax, 12.4, 9.2, 12.8, 8.7)

# ModelFactory -> Settings
draw_arrow(ax, 11.5, 9.4, 11.5, 5.7)

# Settings -> .env
draw_arrow(ax, 12.4, 5.1, 13.0, 5.1)

# Agent -.-> RAG / Memory (虚线)
draw_dashed_arrow(ax, 7.9, 7.8, 9.2, 7.1)
draw_dashed_arrow(ax, 7.9, 7.6, 13.0, 7.1)

# ========== 图例 ==========
legend_x = 0.8
legend_y = 2.8
ax.text(legend_x, legend_y + 0.8, '图例', fontsize=11, weight='bold', color='#2C3E50')
draw_box(ax, legend_x, legend_y, 1.2, 0.5, '已实现', colors['skill_done'], colors['border_skill_done'], fontsize=9)
draw_box(ax, legend_x + 1.6, legend_y, 1.2, 0.5, '进行中', '#FFF3CD', '#FFC107', fontsize=9)
draw_box(ax, legend_x + 3.2, legend_y, 1.2, 0.5, '预留接口', colors['skill_todo'], colors['border_skill_todo'], linestyle='--', fontsize=9)

# 阶段说明
ax.text(0.8, 1.8, '当前阶段：第一阶段 MVP 骨架搭建（已完成）', fontsize=10, weight='bold', color='#28A745')
ax.text(0.8, 1.3, '   已完成：项目脚手架、ModelFactory、AgentOrchestrator、StandupSkill、CLI、HTTP API', fontsize=9, color='#555')
ax.text(0.8, 0.8, '   预留接口：RAG 知识库 (第三阶段) · 记忆系统 (第四阶段) · 更多 Skill (第二阶段)', fontsize=9, color='#888')

plt.tight_layout()
plt.savefig('docs/architecture.png', dpi=200, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.close()
print('架构图已保存至 docs/architecture.png')
