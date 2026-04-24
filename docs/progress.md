# 开发进度追踪

## 总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | 基础骨架（结构、配置、入口） | ✅ 完成 |
| 2 | 文生图 MVP | ✅ 完成 |
| 3 | 图生图 | ✅ 完成 |
| 4 | 收尾增强 | ✅ 完成 |
| 5 | 双 Provider 架构 + ## 命令 | ✅ 完成 |
| -- | 运行时验证 | ⬜ 待验证 |

---

## 阶段 1：基础骨架 ✅

**日期：** 2026-04-23

**已完成：**
- [x] `metadata.yaml` — 插件元数据
- [x] `_conf_schema.json` — 全量配置 schema（API Key、模型、触发词、风格、并发等）
- [x] `requirements.txt` — 依赖声明（httpx, aiofiles, Pillow）
- [x] `main.py` — 插件入口，含:
  - `@register` 注册 + `Star` 类继承
  - 命令路由：`/draw`, `/imgedit`, `/drawraw`
  - 聊天触发：`on_message` 检测"帮我画"、"帮我改图"
  - 文生图/图生图核心流程骨架
  - 临时文件保存与清理
  - 定时残留清理协程
- [x] `src/provider/gemini.py` — Gemini 3.1 Flash Image REST API 封装（文生图 + 图生图）
- [x] `src/task/manager.py` — 并发控制（Semaphore）+ 自动重试（指数退避）
- [x] `src/storage/state.py` — 任务状态内存存储
- [x] `src/prompt/agent.py` — Prompt Agent 骨架（降级模式：原文直出）
- [x] `src/temp/` — 临时图片目录

---

## 阶段 2：文生图 MVP ✅

**日期：** 2026-04-23

**已完成：**
- [x] Gemini provider 文生图已实现（`text_to_image`）
- [x] `/draw` 命令链路已连通 main.py → provider
- [x] 临时文件保存与发后删除
- [x] Prompt Agent 接入 AstrBot LLM（`context.llm_generate()`）
- [x] prompt 改写系统提示词（文生图/图生图两套模板）
- [x] 三种模式：conservative / enhanced / creative
- [x] 风格预设注入（realistic / anime / watercolor / cinematic / illustration）
- [x] 中文简述返回
- [x] LLM 返回解析 + 降级兜底

---

## 阶段 3：图生图 ✅

**日期：** 2026-04-23

**已完成：**
- [x] Gemini provider 图生图已实现（`image_to_image`）
- [x] `/imgedit` 命令
- [x] 聊天触发"帮我改图"
- [x] 从用户消息中提取图片（`Image.convert_to_base64()`）

---

## 阶段 4：收尾增强 ✅

**日期：** 2026-04-23

**已完成：**
- [x] 全量配置 schema（`_conf_schema.json`）
- [x] 并发控制（`asyncio.Semaphore`）
- [x] 自动重试（指数退避）
- [x] 残留文件定时清理
- [x] Prompt Agent 三种模式切换
- [x] `/drawraw` 命令（跳过 LLM 扩写直接生图）
- [x] `show_final_prompt` 配置在返回中的展示
- [x] base64 data URI 前缀处理（兼容 convert_to_base64 带前缀的情况，provider + _save_temp 双保险）
- [x] TaskManager 并发控制/重试逻辑接入主流程

---

## 阶段 5：双 Provider 架构 + ## 命令 ✅

**日期：** 2026-04-24

**背景：** 实际测试中发现：① AstrBot 无 Gemini 专用 provider，用户使用 OpenAI 兼容的中转站；② 自动发现 API Key 失败；③ 需要支持非 Gemini 模型作为备选。

**已完成：**
- [x] `src/provider/base.py` — `ImageProvider` 抽象基类，定义 `text_to_image` / `image_to_image` 接口
- [x] `src/provider/openai.py` — OpenAI 兼容格式 Provider（`/v1/images/generations`），含尺寸映射
- [x] `src/provider/gemini.py` — 重构为继承 `ImageProvider`，移除自动发现和 proxy
- [x] 命令前缀从 `/` 改为 `##`：`##draw` / `##imgedit` / `##drawraw`
- [x] 移除中文聊天触发词（"帮我画"、"帮我改图"）
- [x] 移除 `proxy_url` 配置项
- [x] `provider_id`（`_special: select_provider`）下拉选择 AstrBot 模型提供商
- [x] `provider_endpoint_url` — 手动覆盖 API 端点
- [x] `options` 下拉选择器 — style_preset / prompt_mode / aspect_ratio / image_size
- [x] `fallback_api_key` / `fallback_api_url` / `fallback_model` 备用配置段（invisible）
- [x] Provider 自动发现逻辑（`_resolve_provider`）：选择 → 自动发现 → 备用
- [x] Provider 类型自动识别（Gemini vs OpenAI）
- [x] 无 Provider 时命令提示"插件未配置"
- [x] `##imgedit` 对非 Gemini provider 提示"不支持图生图"
- [x] 所有文档已更新（README, dev_guide, progress）

**设计决策：**
- 双 provider 并存：GeminiProvider（主要，完整功能） + OpenAIProvider（备用，仅文生图）
- 类型识别基于 `meta().type`：
  - 含 `google` / `gemini` → GeminiProvider（使用 Gemini REST API）
  - 其他类型 → OpenAIProvider（使用 OpenAI 兼容接口）
- 图生图仅 Gemini 支持，OpenAI 尝试 `/v1/images/edits` 但不保证兼容
- `style_preset` / `custom_style_prompt` / `aspect_ratio` 保留但仅 Gemini 生效
- 代理交由系统环境变量 `http_proxy` / `https_proxy`

**待验证：**
- [ ] 通过 `_special: select_provider` 选择中转站 provider 后能否正常文生图
- [ ] 备用配置直接填写中转站 API Key + URL 能否工作
- [ ] Gemini API Key 自动发现（有 Google provider 时）
- [ ] `##draw` 命令不带空格能否正确解析（`##draw一只猫`）
- [ ] 无 Provider 时是否给出清晰提示

---

## 待定项

- **验证环境：** 需要 AstrBot 运行环境才能完整验证
- **Image.convert_to_base64() 返回格式：** 参考插件中处理了 `data:image/...` 前缀，Gemini provider 发送时已拼接正确格式
- **OpenAI edits 端点：** `/v1/images/edits` 多数中转站不支持，图生图实际仅 Gemini
