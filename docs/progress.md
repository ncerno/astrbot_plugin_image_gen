# 开发进度追踪

## 总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | 基础骨架（结构、配置、入口） | ✅ 完成 |
| 2 | 文生图 MVP | ✅ 完成 |
| 3 | 图生图 | ✅ 完成 |
| 4 | 收尾增强 | ✅ 完成 |
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

**下一步：** 实现 Prompt Agent 的 LLM 调用，将中文改写为英文 prompt

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

**关键确认：**
- `Context.llm_generate()` 方法用于调用 AstrBot 当前 LLM
- `context.get_all_providers()` 获取可用 provider 列表
- `context.get_current_chat_provider_id(umo)` 获取当前会话使用的 provider

---

## 阶段 3：图生图 ✅

**已完成：**
- [x] Gemini provider 图生图已实现（`image_to_image`）
- [x] `/imgedit` 命令
- [x] 聊天触发"帮我改图"
- [x] 从用户消息中提取图片（`Image.convert_to_base64()`）

**注意：**
- Gemini 3.1 Flash Image 的图生图是编辑模式：传入参考图 + 修改描述，模型自动处理
- 不是独立的两阶段流程，而是单次 API 调用

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
- [x] 基础64 data URI 前缀处理（兼容 convert_to_base64 带前缀的情况，provider + _save_temp 双保险）
- [x] TaskManager 并发控制/重试逻辑接入主流程（原代码直接调 provider 跳过了 task_manager）

**待完成：**
- [ ] 完整运行时验证（需要 AstrBot 环境 + Gemini API Key + 代理）

---

## 待定项

- **代理问题：** `ai.google.dev` 国内网络不可直接访问。插件通过 `proxy_url` 配置项支持代理
- **验证环境：** 需要 AstrBot 运行环境 + 配置 Gemini API Key + 代理才能完整验证
- **Image.convert_to_base64() 返回格式：** 参考插件中处理了 `data:image/...` 前缀，Gemini provider 发送时已拼接正确格式
