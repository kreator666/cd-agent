# 任务执行记录

## 任务信息
- **阶段**: 第二阶段 —— Skill 与前端扩展
- **任务编号**: 2.6
- **任务名称**: 生成脱口秀视频
- **执行日期**: 2026-10-27

## 任务说明
在「笑果评测」页面为已生成的段子增加「生成脱口秀视频」能力。用户点击后进入视频工作台，可基于段子文案自动生成一段竖屏短视频（多场景插画轮播 + 动态字幕 + TTS 配音）。

实现方案（方案 A）：
- 分镜：按中文标点切分并合并为 3-7 个镜头。
- 画面：调用 302.AI `gpt-image-2` 文生图，失败时降级为纯色占位图。
- 配音：使用本地 `edge-tts` 生成，降低 API 消耗。
- 合成：MoviePy 2.x 竖屏 1080×1920，底部字幕区 + 插画 + 装饰线。
- BGM：暂不内置，工作台开关默认关闭。

## 完成内容
- 新增 `VideoJob` 表，记录任务状态、分镜、资产路径、最终视频路径等。
- 更新 `Settings`，增加 `AI302_API_KEY`、`video_output_dir`、`video_bgm_dir`。
- 新增 `src/comedy_agent/services/ai302_client.py`：302.AI 文生图/TTS 客户端。
- 新增 `src/comedy_agent/services/video_generator.py`：五阶段视频生成服务（script/assets/storyboard/video/post）。
- 新增 `src/comedy_agent/api/routers/video.py`：`POST /video/jobs`、`GET /video/jobs/{job_id}`、`GET /video/jobs/{job_id}/download`、`GET /video/jobs`。
- 在 `src/comedy_agent/api/server.py` 注册 video router。
- 新增 `GET /eval/results/{result_id}`，供工作台读取段子原文。
- 新增 `frontend/video-workbench.html` 视频工作台页面。
- 在 `frontend/eval.html` 结果卡片增加 🎬 生成视频按钮。
- 新增 `tests/test_video_generator.py`，使用 mock 替代 302.AI 与 TTS，不消耗 Token。
- 配置 `.env.example` 增加 `AI302_API_KEY` 占位。
- 专业版入口已在导航栏隐藏（`style="display:none;"`）。

## Commit 记录
- **Commit ID**: `a6b5cbd42fe54b1a98e764197d9970838d01a317`
- **Commit Message**: `task 2.6: 生成脱口秀视频`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 后续修复与补充
1. **修复视频无法播放/下载**（Commit `22ef921`）
   - 原因：`/video/jobs/{job_id}/download` 需要鉴权，浏览器 `<video>` 标签与下载链接无法携带 Token。
   - 方案：在 `server.py` 挂载 `/static/video` 到 `video_output_dir`，`video.py` 统一返回 `/static/video/...` URL。

2. **新增「我的视频」列表页并避免重复生成**（Commit `d0db6e2`）
   - 新增 `frontend/video-list.html`，展示所有视频任务，支持播放、下载、重新生成。
   - `eval.html` 结果卡片根据该段子是否已有视频任务动态显示：
     - 已完成 → 「📹 查看视频」跳转到列表
     - 生成中 → 「⏳ 视频生成中」跳转到列表
     - 未生成 → 「🎬 生成视频」进入工作台
   - `video-workbench.html` 顶部与侧边栏增加「我的视频」入口。
   - `VideoJob` 增加与 `EvalResult` 的关联，`/video/jobs` 返回 `result_content` 便于列表展示原文。

## 备注
- 测试通过率：
  - `tests/test_annotation_api.py` + `tests/test_api_new_routers.py`：17/17 通过
  - `tests/test_video_generator.py`：1/1 通过
- 端到端验证：在本地启动服务后，使用 `testresult01` 创建视频任务 `ff9ae16f31334ee1`，最终生成 428KB 可播放 MP4。
- 测试期间 302.AI 文生图因环境 SSL 握手问题 (`UNEXPECTED_EOF_WHILE_READING`) 自动降级为占位图，但流水线完整跑通。
- API Key 仅在本地测试时使用，未提交到代码仓库。
