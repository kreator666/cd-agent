# 极速版"一键生成"完整调用链路

## 1. 前端请求

用户点击按钮后，前端 `POST /speed/polish`，携带：
- `text` — 原文
- `intensity` — 强度（light/medium/heavy）
- `ip_role_id` — 可选的大V角色 ID
- `model` — 可选的模型覆盖

---

## 2. 路由层校验（`speed_polish`）

1. 检查 `AgentOrchestrator` 和 `Memory` 就绪
2. 根据强度计算 cost：`light=10 / medium=20 / heavy=30` Token
3. 校验用户 Token 余额（`get_token_account`），不足返回 402

---

## 3. 模型选择

优先级由高到低：
1. `request.model`（单次传入）
2. 用户偏好配置 `speed_model`
3. 系统默认模型

---

## 4. IP 角色加载

1. 先查 `IPStyle` 表（`load_ip_style`）
2. 未命中则查大V用户（`get_user` + `is_verified`）
3. 提取风格提示：
   - IPStyle → `prompt_snippet`
   - 大V用户 → `bio`（个人简介）

---

## 5. 构造 Prompt

```
使用 add_salt 技能 来对以下文本进行幽默润色。

原文：xxx
强度：medium
角色风格：xxx（若选了角色）
```

---

## 6. AgentOrchestrator 调度

`orch.run(prompt, user_id=user_id)`

| 步骤 | 方法 | 说明 |
|------|------|------|
| 6.1 | `_parse_skill_directive` | 从 prompt 中解析出 "add_salt" 技能 |
| 6.2 | `_invoke_directive_skill` | 直接调用 `AddSaltSkill`，**不走** Agent 自动路由 |
| 6.3 | `_extract_skill_args` | 用 LLM 将 prompt 提取为 JSON 参数：`text`、`intensity`、`ip_role_prompt` |

---

## 7. Skill 执行（`AddSaltSkill._run`）

| 步骤 | 方法 | 说明 |
|------|------|------|
| 7.1 | `_build_system_prompt` | 基础规则 + IP 角色风格注入（若提供了 `ip_role_prompt`） |
| 7.2 | `_build_user_prompt` | 强度映射（如 medium → "约20% 适度幽默"） |
| 7.3 | `ModelFactory.get_model_with_fallback` | 按 `task_type="fast"` 获取 LLM 实例 |
| 7.4 | `chain.invoke()` | `ChatPromptTemplate \| LLM` 调用模型生成润色文本 |

---

## 8. 收尾

1. **Token 预估**：字符数 × 0.8
2. **扣费**：`deduct_tokens(user_id, cost)`
3. **保存记录**：`save_conversation(source="speed")`
4. **返回**：`SpeedPolishResponse`
   - `original` — 原文
   - `polished` — 润色后文本
   - `ip_role` — 使用的 IP 角色信息
   - `token_cost` / `estimated_tokens` — Token 消耗
