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

3. **视频工作台分阶段执行 + AI 修改 + 更多音色**（Commit `0cb7817`）
   - 将视频生成拆分为 5 个可独立执行的节点：剧本分镜 → 画面资产 → 分镜预览 → 视频合成 → 后期配音。
   - 每个节点完成后自动暂停，工作台显示审核面板：
     - 剧本分镜：可编辑文案与画面提示词，支持 AI 优化。
     - 画面资产：可编辑提示词、单镜头重新生成，支持 AI 优化。
     - 分镜预览：可调整每个镜头时长。
     - 视频合成：预览无声视频。
     - 后期配音：可切换音色并重新配音，下载成片。
   - 新增后端接口：
     - `POST /video/jobs/{job_id}/stage/{stage_name}/run`
     - `POST /video/jobs/{job_id}/stage/{stage_name}/edit`
     - `POST /video/jobs/{job_id}/stage/{stage_name}/ai-modify`
   - 配音音色扩展为 19 种，并分组为「女声 / 男声 / 搞笑/特色」。

4. **修复画面资产图片无法显示**（Commit `fc6c777`）
   - 原因：数据库和 storyboard_json 中存的是本地绝对路径（如 `D:\agent\...\images\000.png`），浏览器无法直接访问。
   - 方案：
     - `video_generator.py` 存储相对路径（如 `images/000.png`）。
     - `video.py` 对已有任务的绝对路径做归一化。
     - 前端通过 `/static/video/{job_id}/{相对路径}` 访问图片。
   - 同步修复 `video-list.html` 列表页分镜缩略图。

5. **修复工作台进度丢失并始终显示 5 步时间线**（Commit `8bb51f8`）
   - 原因：从「查看进度」进入工作台时只带 `result_id`，工作台会创建新任务并从第一步开始。
   - 方案：
     - `video-workbench.html` 支持 `job_id` 参数，进入后加载已有任务并定位到当前阶段。
     - 左侧配置面板始终显示 5 个阶段时间线，通过颜色区分 done / active / pending。
     - `eval.html` 与 `video-list.html` 的「查看进度」链接改为 `video-workbench.html?job_id=...`。

6. **修复画面资产每个镜头的图仍不显示，且点击「重新生成此图」无响应**（Commit `ec39660`）
   - 原因：
     - `storyboard_json` 中保存的已经是 `job_id/images/000.png` 相对路径，但前端 `imageUrl()` 又拼了一层 `job_id`，导致请求 `/static/video/{job_id}/{job_id}/images/000.png` 404。
     - 点击「重新生成此图」时，后端下载 302.AI 返回的图片 URL 因环境 SSL 握手失败 (`UNEXPECTED_EOF_WHILE_READING`) 抛异常，前端没有反馈。
   - 方案：
     - `frontend/video-workbench.html` 与 `frontend/video-list.html` 的 `imageUrl()` 改为直接使用后端返回的相对路径，拼接为 `/static/video/${relPath}`。
     - `video-workbench.html` 为「重新生成此图」按钮增加唯一 id，点击后显示「生成中...」并禁用，避免重复提交。
     - `video_generator.py` 的 `regenerate_scene_image()` 增加 try/except，生成失败时自动降级为纯色占位图，确保编辑接口始终返回成功。

7. **修复画面资产 5 个图仍不能显示（路径重复叠加）**（Commit `f2315fc`）
   - 原因：存储路径与重建路径的「根目录」不一致。
     - `_rel_path()` 以 `video_output_dir` 为根，存成 `job_id/images/000.png`。
     - `reconstruct_generator()` 却以 `gen.output_dir`（即 `video_output_dir/job_id`）为根再拼一次，导致每次编辑/重新生成都会多叠加一层 `job_id`，最终出现 `job_id/job_id/.../images/001.png` 这种嵌套路径而 404。
   - 方案：
     - 增加 `_canonical_rel_image_path()` 工具，把重复叠加的 `job_id` 规范化为一层。
     - `reconstruct_generator()` 改用 `video_output_dir` 作为相对路径根目录恢复绝对路径。
     - `video.py` 的 `_normalize_storyboard()` 传入 `job_id`，对绝对路径和已相对路径都统一做规范化，保证前端拿到的始终是 `job_id/images/000.png`。
   - 已对本地的历史任务 `202fde540feb4559` 等执行数据清理，将嵌套路径恢复为规范路径。

8. **修复点击「后期配音」报错 `asyncio.run() cannot be called from a running event loop`**（Commit `4f5f083`）
   - 原因：`add_post_audio()` 内部调用 `asyncio.run(self.generate_tts())`，而 `POST /video/jobs/{job_id}/stage/{stage_name}/run` 是 FastAPI 的异步路由，已经处于运行中的事件循环内，`asyncio.run()` 被禁止嵌套调用。
   - 方案：
     - 新增 `_run_async_sync()` 工具，在独立线程中执行 `asyncio.run(coro)`，既兼容同步调用方，也兼容事件循环内调用。
     - `add_post_audio()` 改用 `_run_async_sync(self.generate_tts())`。
     - 若旧任务缺少 `silent.mp4`，post 阶段自动先补合成无声视频，而不是直接报错。

## 备注
- 测试通过率：
  - `tests/test_annotation_api.py` + `tests/test_api_new_routers.py`：17/17 通过
  - `tests/test_video_generator.py`：1/1 通过
- 端到端验证：在本地启动服务后，使用 `testresult01` 创建视频任务 `ff9ae16f31334ee1`，最终生成 428KB 可播放 MP4。
- 测试期间 302.AI 文生图因环境 SSL 握手问题 (`UNEXPECTED_EOF_WHILE_READING`) 自动降级为占位图，但流水线完整跑通。
- API Key 仅在本地测试时使用，未提交到代码仓库。
