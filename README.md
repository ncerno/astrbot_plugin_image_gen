# astrbot_plugin_image_gen

基于 **Gemini 3.1 Flash Image** 和 **OpenAI 兼容 API** 的 AstrBot 文生图/图生图插件。

## 功能

- **文生图** — 输入描述，AI 生成图片（支持 Gemini + OpenAI 兼容接口）
- **图生图** — 发送参考图 + 修改描述，AI 编辑图片（仅 Gemini）
- **Prompt 自动改写** — 输入中文，LLM 自动扩写为英文 prompt，提升出图质量
- **风格预设** — realistic / anime / watercolor / cinematic / illustration（仅 Gemini）
- **双 Provider 支持** — 可选用 AstrBot 中已配置的 provider，也可手动配置备用
- **并发控制 & 自动重试** — 避免 API 过载，网络波动自动重试

## 部署指南

### 前提条件

1. 已部署 [AstrBot](https://github.com/AstrBotDevs/AstrBot)（≥ v4.16）
2. 在 AstrBot 管理面板中已添加至少一个模型提供商并配置好 API Key
3. 部署机器可访问相应的 API 端点（国内机器使用中转站或代理）

### 安装步骤

**方式一：AstrBot 管理面板安装（推荐）**

1. 打开 AstrBot 管理面板 →「插件管理」
2. 点击「安装插件」→「从 GitHub 安装」
3. 输入仓库地址：`https://github.com/ncerno/astrbot_plugin_image_gen`
4. 点击安装，等待完成

**方式二：手动安装**

```bash
cd AstrBot/addons/
git clone https://github.com/ncerno/astrbot_plugin_image_gen.git
cd astrbot_plugin_image_gen
pip install -r requirements.txt
```

重启 AstrBot。

### 配置说明

安装后，在 AstrBot 管理面板找到「图片生成」插件。

#### 核心配置

| 配置项 | 说明 |
|--------|------|
| `provider_id` | 选择 AstrBot 中已配置的模型提供商。插件自动获取 Key 和端点 |
| `model` | 图像模型名称。Gemini：`gemini-3.1-flash-image-preview`；OpenAI：`dall-e-3` |
| `provider_endpoint_url` | 自动获取端点失败时手动填写 API URL |

#### 常用配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `style_preset` | `auto` | 风格预设（仅 Gemini）。auto / realistic / anime / watercolor / cinematic / illustration |
| `prompt_mode` | `enhanced` | 改写模式：conservative / enhanced / creative |
| `aspect_ratio` | `1:1` | 图片比例（仅 Gemini） |
| `image_size` | `1K` | 分辨率：512 / 1K / 2K / 4K |
| `global_concurrency` | `3` | 同时处理的生图任务数 |

#### 备用配置（自动发现失败时使用）

| 配置项 | 说明 |
|--------|------|
| `fallback_api_key` | 手动配置 API Key |
| `fallback_api_url` | 手动配置 API 端点 URL |
| `fallback_model` | 手动配置模型名 |

完整配置项见 `_conf_schema.json`。

## 使用方法

### 命令

| 命令 | 说明 |
|------|------|
| `##draw 一只机械猫在雨夜的城市中` | 文生图 |
| `##drawraw cyberpunk city street rain` | 跳过 LLM 改写，直接生图 |
| `##imgedit 把背景换成雪山` | 图生图（需同时发送参考图片，仅 Gemini） |

命令前缀 `##` 为固定格式，命令名称可在配置中修改。

### 图片要求（图生图）

仅支持 **JPG/PNG** 格式，单张图片大小不超过 **10MB**。

### 返回说明

- 每次生成返回：图片 + 中文简述
- 可在配置中开启 `show_final_prompt`，额外显示最终提交的英文 prompt

## 常见问题

**Q：插件提示"未配置 Provider"？**
A：在 AstrBot 管理面板 →「模型提供商」中添加一个提供商（Gemini 或 OpenAI 兼容），然后在插件配置的 `provider_id` 下拉中选择它。如果自动获取失败，填写备用配置中的 API Key 和 URL。

**Q：API Key 在哪里配置？**
A：在 AstrBot 管理面板中配置模型提供商时填入。插件通过 `provider_id` 选择后自动获取，无需在插件中重复填写。也可以直接在插件备用配置中填写。

**Q：中转站怎么配置？**
A：在 AstrBot 中添加 OpenAI 兼容的提供商（填入中转站地址和 Key），然后在插件 `provider_id` 中选择它。如果自动获取 URL 失败，在 `provider_endpoint_url` 中手动填入中转站地址。

**Q：生成的图片质量不理想？**
A：尝试切换到更详细的 prompt 模式：将 `prompt_mode` 设为 `creative`，或使用风格预设（仅 Gemini）。

**Q：图生图不支持？**
A：图生图仅 Gemini 模型的 `##imgedit` 命令支持。使用 OpenAI 兼容接口时，`##imgedit` 不可用。

## 技术栈

- Python 3.10+
- AstrBot Star API
- Gemini 3.1 Flash Image API / OpenAI Images API
- httpx（异步 HTTP 请求）
