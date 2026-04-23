# astrbot_plugin_image_gen

基于 **Gemini 3.1 Flash Image** 的 AstrBot 文生图/图生图插件。

## 功能

- **文生图** — 输入描述，AI 生成图片
- **图生图** — 发送参考图 + 修改描述，AI 编辑图片
- **Prompt 自动改写** — 输入中文，LLM 自动扩写为英文 prompt，提升出图质量
- **风格预设** — realistic / anime / watercolor / cinematic / illustration
- **并发控制 & 自动重试** — 避免 API 过载，网络波动自动重试

## 部署指南

### 前提条件

1. 已部署 [AstrBot](https://github.com/AstrBotDevs/AstrBot)（≥ v4.16）
2. 拥有 [Gemini API Key](https://aistudio.google.com/apikey)（需科学上网获取）
3. 部署机器可访问 `generativelanguage.googleapis.com`（国内机器需配置代理）

### 安装步骤

**方式一：AstrBot 管理面板安装（推荐）**

1. 打开 AstrBot 管理面板 →「插件管理」
2. 点击「安装插件」→「从 GitHub 安装」
3. 输入仓库地址：`https://github.com/ncerno/astrbot_plugin_image_gen`
4. 点击安装，等待完成

**方式二：手动安装**

1. 进入 AstrBot 的 `addons/` 目录
2. 克隆仓库：

```bash
cd addons/
git clone https://github.com/ncerno/astrbot_plugin_image_gen.git
```

3. 安装依赖：

```bash
cd astrbot_plugin_image_gen
pip install -r requirements.txt
```

4. 重启 AstrBot

### 配置说明

安装后，在 AstrBot 管理面板找到「图片生成」插件，填写以下配置：

#### 必填项

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `api_key` | Gemini API Key | [Google AI Studio](https://aistudio.google.com/apikey) |

#### 网络配置（国内机器必填）

| 配置项 | 说明 |
|--------|------|
| `proxy_url` | HTTP 代理地址，如 `http://127.0.0.1:7890`。留空表示直连 |

如果 AstrBot 本身已配置环境变量代理（`http_proxy`/`https_proxy`），此项可留空。

#### 常用配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `style_preset` | `auto` | 默认风格：auto / realistic / anime / watercolor / cinematic / illustration |
| `prompt_mode` | `enhanced` | 改写模式：conservative（保守）/ enhanced（增强）/ creative（创意） |
| `aspect_ratio` | `1:1` | 图片比例：1:1 / 16:9 / 4:3 / 3:2 / 3:4 / 9:16 |
| `image_size` | `1K` | 分辨率：512 / 1K / 2K / 4K |
| `global_concurrency` | `3` | 同时处理的生图任务数 |

完整配置项见 `_conf_schema.json`。

## 使用方法

### 命令

| 命令 | 说明 |
|------|------|
| `/draw 一只机械猫在雨夜的城市中` | 文生图 |
| `/drawraw cyberpunk city street rain` | 跳过 LLM 改写，直接生图（需英文 prompt） |
| `/imgedit 把背景换成雪山` | 图生图（需同时发送参考图片） |

### 聊天触发（无需命令）

在聊天中直接发送：

- `帮我画一只柴犬穿着西装` — 触发文生图
- `帮我改图 把背景换成雪山` — 触发图生图（需同时发送图片）

### 返回说明

- 每次生成返回：图片 + 中文简述
- 可在配置中开启 `show_final_prompt`，额外显示最终提交给 Gemini 的英文 prompt

## 常见问题

**Q：生成失败，提示网络错误？**
A：国内机器访问 Google API 需要代理。在配置中设置 `proxy_url`，如 `http://127.0.0.1:7890`。

**Q：API Key 怎么获取？**
A：访问 https://aistudio.google.com/apikey ，登录 Google 账号后点击「Create API Key」。

**Q：提示"API Key 未配置"？**
A：安装后在管理面板的插件配置中填入 `api_key`，然后重启 AstrBot。

**Q：生成的图片质量不理想？**
A：尝试切换到更详细的 prompt 模式：将 `prompt_mode` 设为 `creative`，或使用风格预设。

## 技术栈

- Python 3.10+
- AstrBot Star API
- Gemini 3.1 Flash Image API
- httpx（异步 HTTP 请求）
