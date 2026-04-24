# AstrBot × Gemini 3.1 Flash Image 插件开发技术参考

> 基于官方文档与参考插件源码整理，版本确认日期：2026-04-23

---

## 目录结构

```
astrbot_plugin_image_gen/
├── main.py                    # 插件入口（必须叫 main.py）
├── metadata.yaml              # 插件元数据（必填）
├── _conf_schema.json          # 配置 schema
├── requirements.txt           # pip 依赖
│
├── prompt/
│   └── agent.py               # Prompt Agent 模块
├── provider/
│   ├── __init__.py
│   ├── base.py                # ImageProvider 抽象基类
│   ├── gemini.py              # Gemini 3.1 Flash Image 封装
│   └── openai.py              # OpenAI 兼容格式封装
├── task/
│   └── manager.py             # 异步任务管理（并发 + 重试）
├── storage/
│   └── state.py               # 任务状态内存存储
└── temp/
    └── .gitkeep               # 临时图片目录
```

---

## 一、插件注册与骨架

### 1.1 metadata.yaml

插件根目录下必须包含此文件，AstrBot 依赖它识别插件。

```yaml
name: astrbot_plugin_image_gen
desc: 基于 Gemini 3.1 Flash Image 的文生图/图生图插件
version: v0.1.0
author: YourName
repo: https://github.com/xxx/astrbot_plugin_image_gen
```

推荐附加字段：

```yaml
display_name: 图片生成           # 展示名，可选
support_platforms:              # 支持平台声明，可选
  - qq_official
  - aiocqhttp
astrbot_version: ">=4.16"      # 版本约束，可选
```

`support_platforms` 可选值：`aiocqhttp`, `qq_official`, `telegram`, `wecom`, `lark`, `dingtalk`, `discord`, `slack`, `kook`, `vocechat`, `weixin_official_account`, `satori`, `misskey`, `line`

### 1.2 main.py — 插件入口

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

from src.prompt.agent import PromptAgent
from src.provider.gemini import GeminiProvider
from src.provider.openai import OpenAIProvider
from src.provider.base import ImageProvider

@register(
    "astrbot_plugin_image_gen",     # 插件名
    "nero",                          # 作者
    "基于 Gemini / OpenAI 兼容 API 的文生图/图生图插件",
    "0.2.0"                          # 版本
)
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # config 来自 _conf_schema.json，已被框架自动加载
        # 通过 _resolve_provider() 自动选择合适的 provider
        self.provider: ImageProvider | None = self._resolve_provider(context, config)

    async def initialize(self):
        """可选的异步初始化方法"""
        logger.info("图片生成插件已加载")

    async def terminate(self):
        """可选的销毁方法"""
        logger.info("图片生成插件已卸载")
```

---

## 二、消息处理

### 2.1 命令注册

本插件使用 `##` 前缀命令，通过 `on_message` 统一处理，而非 `@filter.command`。

```python
async def on_message(self, event: AstrMessageEvent):
    """监听 ##draw / ##imgedit / ##drawraw 命令"""
    text = event.message_str.strip()

    # 按最长前缀优先匹配
    if text.startswith("##" + self.drawraw_cmd):
        prompt = text[len("##" + self.drawraw_cmd):].strip()
        if prompt:
            async for result in self._handle_text2img(event, prompt, skip_prompt_agent=True):
                yield result
        return

    if text.startswith("##" + self.imgedit_cmd):
        prompt = text[len("##" + self.imgedit_cmd):].strip()
        if prompt:
            async for result in self._handle_img2img(event, prompt):
                yield result
        return

    if text.startswith("##" + self.draw_cmd):
        prompt = text[len("##" + self.draw_cmd):].strip()
        if prompt:
            async for result in self._handle_text2img(event, prompt):
                yield result
        return
```

**设计说明**：
- 固定前缀 `##` + 可配置命令名（`draw_command` / `imgedit_command` / `drawraw_command`）
- 命令与描述之间**不需要空格**：`##draw一只猫` 和 `##draw 一只猫` 均可
- 使用 `on_message` 而非 `@filter.command`，因为后者默认使用 `/` 前缀且不可按需修改

### 2.2 消息监听方法

```python
async def on_message(self, event: AstrMessageEvent):
    """监听所有消息（群聊+私聊），用于解析 ## 命令"""
    # 按 ## 前缀检测命令
    pass

async def on_private_message(self, event: AstrMessageEvent):
    """仅私聊消息"""
    pass

async def on_all_message(self, event: AstrMessageEvent):
    """群聊+私聊（比 on_message 覆盖更广）"""
    pass
```

**注意**：本插件不使用中文聊天触发词（"帮我画"、"帮我改图"等），全部通过 `##draw` / `##imgedit` / `##drawraw` 命令触发。

### 2.3 事件钩子系统

钩子不支持与 `@filter.command` / `@filter.command_group` 等装饰器混用。

**常用钩子**：

```python
# Bot 初始化完成
@filter.on_llm_request
async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
    """LLM 请求前触发，可修改 req.system_prompt 等"""
    pass

@filter.on_llm_response
async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
    """LLM 请求完成后触发"""
    pass

@filter.on_waiting_llm_request
async def on_waiting_llm(self, event: AstrMessageEvent):
    """等待 LLM 请求时触发"""
    await event.send("正在等待请求...")  # 注意：此处不能用 yield
```

事件钩子装饰器一览：

| 装饰器 | 触发时机 | 额外参数 |
|--------|----------|----------|
| `@filter.on_llm_request` | LLM 请求前 | `req: ProviderRequest` |
| `@filter.on_llm_response` | LLM 完成后 | `resp: LLMResponse` |
| `@filter.on_agent_begin` | Agent 开始运行时 | `run_context: ContextWrapper[AstrAgentContext]` |
| `@filter.on_using_llm_tool` | LLM 工具调用前 | `tool_name: str`, `tool_args: dict` |
| `@filter.on_waiting_llm_request` | 等待 LLM 锁时 | 无 |

### 2.4 事件过滤器装饰器

```python
@filter.event_message_type("private")    # 仅私聊
@filter.event_message_type("group")      # 仅群聊
@filter.platform_adapter_type("aiocqhttp")  # 仅特定平台
@filter.permission_type("admin")         # 仅管理员
```

这些过滤器可以组合使用：

```python
@filter.command("draw")
@filter.event_message_type("group")
async def draw_in_group(self, event: AstrMessageEvent, prompt: str = ""):
    """仅在群聊中可用的 /draw 命令"""
    pass
```

---

## 三、消息发送

### 3.1 发送纯文本

```python
# 方式一：plain_result（推荐）
yield event.plain_result("Hello!")

# 方式二：chain_result + Plain
from astrbot.api.message_components import Plain
yield event.chain_result([Plain("Hello!")])

# 方式三：直接 send（非 yield 场景，如钩子函数内）
await event.send("Hello!")
```

### 3.2 发送图片

导入方式有两种：

```python
# 方式 A：从 message_components 导入
from astrbot.api.message_components import Image, Plain

# 方式 B：从 all 导入
from astrbot.api.all import Image, Plain
```

**图片发送方式**：

```python
# 从本地文件发送（推荐）
image = Image.fromFileSystem("path/to/image.jpg")

# 从 URL 发送
image = Image.fromURL("https://example.com/image.jpg")
```

**组合文本+图片**：

```python
yield event.chain_result([
    Plain("生成完成！\n描述：一只雨夜中的猫"),
    Image.fromFileSystem("src/temp/generated_12345.png")
])
```

### 3.3 其他消息组件

```python
import astrbot.api.message_components as Comp

# 文本
Comp.Plain("文字内容")

# 图片
Comp.Image.fromFileSystem("path")
Comp.Image.fromURL("url")

# @ 某人
Comp.At(qq=event.get_sender_id())

# 回复
Comp.Reply()

# 视频
Comp.Video.fromFileSystem(path="path/to/video.mp4")
Comp.Video.fromURL(url="https://example.com/video.mp4")

# 语音
Comp.Record(file="path/to/audio.mp3", url="https://example.com/audio.mp3")

# 文件
Comp.File(file="path/to/file.pdf")

# 合并转发节点
from astrbot.api.message_components import Node
node = Comp.Node(
    users=[{"name": "UserA"}, {"name": "UserB"}],
    content=[Comp.Plain("消息内容")]
)
```

### 3.4 MessageChain 构建器

```python
from astrbot.api.message_components import MessageChain

chain = MessageChain() \
    .message("Hello!") \
    .file_image("path/to/image.jpg") \
    .url_image("https://example.com/image.jpg")

# 然后使用 chain_result 发送
yield event.chain_result(chain.chain)  # chain.chain 返回组件列表
```

---

## 四、图片提取（从用户消息中读取图片）

### 4.1 基础图片提取

适用于通过 `/draw` 命令发送图片（前面有图片）的情况：

```python
@filter.command("draw")
async def draw(self, event: AstrMessageEvent, prompt: str = ""):
    images = []

    if hasattr(event, "message_obj") and event.message_obj:
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                try:
                    base64_data = await comp.convert_to_base64()
                    images.append(base64_data)
                except Exception as e:
                    logger.warning(f"图片转 base64 失败: {e}")

    if images:
        # 图生图模式
        pass
    else:
        # 文生图模式
        pass
```

### 4.2 引用消息图片提取

用户回复某条图片消息时使用：

```python
from astrbot.api.message_components import Reply

for comp in event.message_obj.message:
    if isinstance(comp, Reply) and comp.chain:
        for reply_comp in comp.chain:
            if isinstance(reply_comp, Image):
                base64_data = await reply_comp.convert_to_base64()
                images.append(base64_data)
```

### 4.3 消息结构说明

`event.message_obj` 的结构：

```python
event.message_obj.message    # 消息组件列表 [Plain, Image, At, ...]
event.message_str            # 纯文本内容（去除图片等组件后的文字）
event.get_sender_name()      # 发送者名称
event.get_sender_id()        # 发送者 QQ
event.unified_msg_origin     # 消息源标识（用于定位回话）
```

---

## 五、插件配置

### 5.1 _conf_schema.json

在插件根目录下创建此文件，定义配置项的结构。

```json
{
  "schema": {
    "provider_id": {
      "type": "string",
      "_special": "select_provider",
      "description": "选择 AstrBot 中已配置的模型提供商",
      "default": ""
    },
    "model": {
      "type": "string",
      "description": "图像模型名称（Gemini: gemini-3.1-flash-image-preview, OpenAI: dall-e-3）",
      "default": "gemini-3.1-flash-image-preview"
    },
    "provider_endpoint_url": {
      "type": "string",
      "description": "手动指定 API 端点 URL（自动获取失败时填写）",
      "default": ""
    },
    "style_preset": {
      "type": "string",
      "options": ["auto", "realistic", "anime", "watercolor", "cinematic", "illustration"],
      "description": "风格预设（仅 Gemini 有效）",
      "default": "auto"
    },
    "prompt_mode": {
      "type": "string",
      "options": ["conservative", "enhanced", "creative"],
      "description": "Prompt 改写模式",
      "default": "enhanced"
    },
    "aspect_ratio": {
      "type": "string",
      "options": ["1:1", "16:9", "4:3", "3:2", "3:4", "4:5", "9:16", "21:9"],
      "description": "图片宽高比（仅 Gemini 有效）",
      "default": "1:1"
    },
    "fallback_api_key": {
      "type": "string",
      "description": "备用 API Key",
      "default": "",
      "invisible": true
    },
    "fallback_api_url": {
      "type": "string",
      "description": "备用 API URL",
      "default": "",
      "invisible": true
    }
  }
}
```

**配置项类型**：`string`, `text`, `int`, `float`, `bool`, `object`, `list`, `dict`, `template_list`, `file`

**下拉选择器**：`options` 字段定义下拉选项列表。

**特殊字段 `_special`**：
- `select_provider` — 下拉选择 AstrBot 已配置的模型提供商
- `select_provider_tts` / `select_provider_stt` — TTS/STT 提供商
- `select_persona` / `select_knowledgebase` — 人格/知识库

**隐藏字段**：`"invisible": true` 在 WebUI 中隐藏（适用于备用配置等不常用项）

### 5.2 Provider 自动发现机制

本插件的 `_resolve_provider()` 方法负责选择并初始化图像生成 provider：

1. **用户选择**（`_special: select_provider`）：使用用户选定的 AstrBot provider
2. **自动发现**：遍历所有 AstrBot provider，找到第一个有 API Key 的
3. **备用配置**（`fallback_*`）：以上均失败时使用手动配置

```python
def _resolve_provider(self, context, config) -> ImageProvider | None:
    provider_id = config.get("provider_id", "")

    # 1. 从 AstrBot providers 获取 key 和类型
    api_key, api_url, is_gemini = self._discover_from_astrbot(
        context, provider_id
    )

    # 2. 手动 URL 覆盖
    manual_url = config.get("provider_endpoint_url", "").strip()
    if manual_url:
        api_url = manual_url

    # 3. 自动发现成功则构建 provider
    if api_key:
        return self._build_provider(api_key, api_url, model, config, is_gemini)

    # 4. 备用手动配置
    fallback_key = config.get("fallback_api_key", "")
    fallback_url = config.get("fallback_api_url", "")
    if fallback_key and fallback_url:
        fb_is_gemini = "google" in fallback_url.lower()
        return self._build_provider(fallback_key, fallback_url, model, config, fb_is_gemini)

    return None  # 无可用 provider
```

**类型识别**：通过 `meta().type` 判断：
- 包含 `"gemini"` 或 `"google"` → `GeminiProvider`（使用 Gemini REST API）
- 其他类型 → `OpenAIProvider`（使用 OpenAI 兼容接口）

**自动获取的字段**：

| 字段 | 来源 | Gemini | OpenAI |
|------|------|--------|--------|
| API Key | `provider.get_keys()[0]` | ✅ 用于 Gemini REST API | ✅ 用于 OpenAI 兼容 API |
| 模型名 | `config["model"]` | Gemini 图像模型名 | dall-e-3 或中转站模型 |
| 端点 URL | `provider.base_url` | 固定 Google 端点 | 从 provider 自动获取 |

**备用配置结构**（`invisible: true`）：
```json
{
  "fallback_api_key": "sk-xxx",
  "fallback_api_url": "https://api.openai.com/v1",
  "fallback_model": "dall-e-3"
}
```

### 5.3 访问 AstrBot 全局配置

```python
astrbot_config = self.context.get_config()
callback_api_base = astrbot_config.get("callback_api_base")
```

### 5.4 数据存储目录

```python
from astrbot.api.star import StarTools

data_dir = StarTools.get_data_dir()  # 获取规范的数据存储目录
# 不要将数据存在插件自身目录，防止更新时数据被覆盖
```

---

## 六、Image Provider 架构

### 6.1 抽象基类（base.py）

所有图像生成 provider 继承自 `ImageProvider`：

```python
from abc import ABC, abstractmethod

class ImageProvider(ABC):
    @abstractmethod
    async def text_to_image(self, prompt: str) -> str:
        """文生图：返回 base64 图片数据"""
        ...

    async def image_to_image(self, prompt: str, reference_base64: str) -> str:
        """图生图（可选实现），默认抛出 NotImplementedError"""
        raise NotImplementedError("当前 Provider 不支持图生图")

    @property
    def supports_img2img(self) -> bool:
        return False
```

### 6.2 Provider 路由逻辑

`main.py` 中的 `_resolve_provider()` 根据类型选择：

| AstrBot provider type | 使用的 Provider | 功能 |
|----------------------|----------------|------|
| `googlegenai_chat_completion` (含 google/gemini) | `GeminiProvider` | 文生图 + 图生图 + 风格预设 |
| `openai_chat_completion` 等其他类型 | `OpenAIProvider` | 文生图（仅 text2img） |
| 手动备用配置 | 根据 URL 自动判断 | 含 google → Gemini，否则 OpenAI |

```python
@staticmethod
def _build_provider(api_key, api_url, model, config, is_gemini) -> ImageProvider:
    if is_gemini:
        return GeminiProvider(api_key, model, config)
    else:
        return OpenAIProvider(api_key, api_url, model, config)
```

### 6.3 GeminiProvider

调用 Google Gemini REST API，支持文生图 + 图生图 + 风格预设 + 宽高比。

### 6.4 OpenAIProvider

调用 OpenAI 兼容格式 API（`/v1/images/generations`），仅文生图。

```python
payload = {
    "model": "dall-e-3",
    "prompt": "...",
    "n": 1,
    "size": "1024x1024",
    "response_format": "b64_json",
}
```

**尺寸映射**：将插件的 `aspect_ratio` + `image_size` 转换为 OpenAI 标准分辨率。

**图生图**：调用 `/v1/images/edits`（试验性，多数中转站不支持）。

---

## 七、Gemini 3.1 Flash Image API

### 6.1 模型规格

| 属性 | 值 |
|------|-----|
| Model ID | `gemini-3.1-flash-image-preview` |
| 输入 | Text, Image, PDF |
| 输出 | Image, Text |
| 输入 token 上限 | 131,072 |
| 输出 token 上限 | 32,768 |
| 最大参考图数 | 14 |
| Temperature | 0.0–2.0 (default 1.0) |
| topP | 0.0–1.0 (default 0.95) |
| candidateCount | 1 |
| Knowledge cutoff | 2025-01 |
| Pricing | $0.25/1M tokens (text input) / $0.067 per image |

**不支持**：function calling、caching、code execution、Live API、audio generation

### 6.2 REST API（推荐，不依赖 google-genai SDK）

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent
Content-Type: application/json
x-goog-api-key: YOUR_API_KEY
```

**文生图请求体**：

```json
{
  "contents": [
    {
      "parts": [
        { "text": "A cat sitting in a rainy city street at night, cinematic lighting" }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["Image", "Text"]
  }
}
```

**图生图请求体**（图片编辑）：

```json
{
  "contents": [
    {
      "parts": [
        { "text": "Change the background to a snowy mountain scene" },
        {
          "inline_data": {
            "mime_type": "image/jpeg",
            "data": "<base64_encoded_image>"
          }
        }
      ]
    }
  ]
}
```

**配置 aspect ratio 和分辨率**：

```json
{
  "contents": [{ "parts": [{ "text": "A beautiful landscape" }] }],
  "generationConfig": {
    "responseModalities": ["Image"],
    "imageConfig": {
      "aspectRatio": "16:9",
      "imageSize": "2K"
    }
  }
}
```

支持的 aspect ratios：`"1:1"`, `"1:4"`, `"1:8"`, `"2:3"`, `"3:2"`, `"3:4"`, `"4:1"`, `"4:3"`, `"4:5"`, `"5:4"`, `"8:1"`, `"9:16"`, `"16:9"`, `"21:9"`

支持的 image sizes：`"512"`, `"1K"`, `"2K"`, `"4K"`

### 6.3 响应解析

图片以 base64 形式返回在 `inline_data` 中，文字返回在 `text` 中。

```json
{
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "Here's your image of a cat in a rainy city..."
          },
          {
            "inline_data": {
              "mime_type": "image/png",
              "data": "<base64_image_data>"
            }
          }
        ]
      }
    }
  ]
}
```

### 6.4 Python 实现参考

不使用 google-genai SDK，直接用 httpx/aiohttp 发请求：

```python
import httpx
import base64

async def generate_image(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> dict:
    """
    调用 Gemini 3.1 Flash Image 文生图。
    返回: {"image_base64": "...", "mime_type": "image/png", "text": "..."}
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["Image", "Text"],
            "imageConfig": {
                "aspectRatio": aspect_ratio,
                "imageSize": "1K"
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=120)

    if resp.status_code != 200:
        raise Exception(f"API error: {resp.status_code} {resp.text}")

    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]

    result = {"text": "", "image_base64": None, "mime_type": None}
    for part in parts:
        if "text" in part:
            result["text"] += part["text"]
        elif "inline_data" in part:
            result["image_base64"] = part["inline_data"]["data"]
            result["mime_type"] = part["inline_data"]["mime_type"]

    return result
```

**带参考图的图生图**：

```python
async def edit_image(prompt: str, reference_base64: str, api_key: str,
                     mime_type: str = "image/jpeg") -> dict:
    """
    图生图：基于参考图 + 修改描述生成新图。
    reference_base64: 原始图片的 base64（不含 data:image/... 前缀）
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent"

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": reference_base64
                    }
                }
            ]
        }]
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=120)

    if resp.status_code != 200:
        raise Exception(f"API error: {resp.status_code} {resp.text}")

    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]

    result = {"text": "", "image_base64": None, "mime_type": None}
    for part in parts:
        if "text" in part:
            result["text"] += part["text"]
        elif "inline_data" in part:
            result["image_base64"] = part["inline_data"]["data"]
            result["mime_type"] = part["inline_data"]["mime_type"]

    return result
```

**保存图片到文件**：

```python
import base64
from pathlib import Path

def save_base64_image(base64_str: str, output_path: str) -> str:
    """保存 base64 图片到文件，返回文件路径"""
    image_bytes = base64.b64decode(base64_str)
    Path(output_path).write_bytes(image_bytes)
    return output_path
```

### 6.5 关于"异步任务"的说明

Gemini 3.1 Flash Image API 是同步接口（`generateContent` 返回完整结果），**不涉及轮询**。插件中不需要做"提交任务→轮询状态"的异步机制。

但需要注意：
- 生图可能需要数秒到数十秒，httpx 的 timeout 应设为 120s 以上
- 建议用 `asyncio` 在插件中做异步调用，避免阻塞 AstrBot 事件循环
- 生成期间可以先用 `yield event.plain_result("正在生成...")` 给用户反馈
- 如需并发控制，可以用 `asyncio.Semaphore` 限制并发数

---

## 八、参考插件模式

### 7.1 astrbot_plugin_ai-image (xxuanzQAQ)

使用 OpenAI 兼容接口，核心流程：

```
/image <描述> → 检测是否有图片附件 → 有则图生图，无则文生图
             → 构建 messages 数组
             → 调用 OpenAI 兼容 API (streaming)
             → 从响应中提取图片 (base64 / URL)
             → 保存到本地文件
             → Image.fromFileSystem() 发送
```

**图片检测逻辑**：遍历 `event.message_obj.message` 中的 `Image` 组件，调用 `convert_to_base64()`

**选择模型依据**：根据提示词中是否含"横屏""竖屏"、是否有图片自动切换

### 7.2 astrbot_plugin_gemini_artist (nichinichisou0609)

使用 Google Gemini SDK + OpenRouter，核心特点：

- 支持 `google.genai` SDK 和 `openai` SDK 两种 API 模式
- 使用 `google.genai.types.HttpOptions` 配置 API 调用
- 使用 `PIL.Image` 处理和保存图片
- 使用 `astrbot.core.utils.io.download_file` 下载文件
- 配置文件：`_conf_schema.json` 带完整 UI 配置

---

## 九、临时文件管理

### 8.1 保存与清理策略

```python
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 清理过期文件
async def cleanup_old_files(temp_dir: Path, max_age_minutes: int = 15):
    now = datetime.now()
    cutoff = now - timedelta(minutes=max_age_minutes)
    for f in temp_dir.glob("gen_*.png"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()

# 生成唯一文件名
def gen_temp_path(temp_dir: Path, ext: str = "png") -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = str(uuid.uuid4())[:8]
    return temp_dir / f"gen_{ts}_{uid}.{ext}"
```

### 8.2 发图后立即删除

```python
# 先发图
yield event.chain_result([Plain("完成！"), Image.fromFileSystem(file_path)])
# 再删除
Path(file_path).unlink(missing_ok=True)
```

---

## 十、完整的命令 Handler 示例

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

from src.provider.gemini import GeminiProvider
from src.provider.openai import OpenAIProvider
from src.provider.base import ImageProvider
from src.task.manager import TaskManager
from src.prompt.agent import PromptAgent

import asyncio
from pathlib import Path
import uuid
from datetime import datetime

@register("astrbot_plugin_image_gen", "nero", "图片生成插件", "0.2.0")
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        # 解析 provider（自动 / 手动）
        self.provider: ImageProvider | None = self._resolve_provider(context, config)

        # Prompt Agent + 任务管理
        self.prompt_agent = PromptAgent(context, config)
        self.task_manager = TaskManager(config, self.provider, task_store)

    def _resolve_provider(self, context, config) -> ImageProvider | None:
        """选择 provider：用户选择 → 自动发现 → 备用配置"""
        # 详见 5.2 节
        ...

    async def on_message(self, event: AstrMessageEvent):
        """监听 ##draw / ##imgedit / ##drawraw 命令"""
        text = event.message_str.strip()

        if text.startswith("##drawraw"):
            prompt = text[9:].strip()
            ...
        elif text.startswith("##imgedit"):
            prompt = text[9:].strip()
            ...
        elif text.startswith("##draw"):
            prompt = text[6:].strip()
            ...

    async def _handle_text2img(self, event, prompt, skip_prompt_agent=False):
        """文生图流程"""
        # 1. 检查 provider
        if not self.provider:
            yield event.plain_result("插件未配置")
            return

        # 2. Prompt 改写
        result = await self.prompt_agent.rewrite(prompt, mode="text2img")
        final_prompt = result["final_prompt_en"]

        # 3. 通过 TaskManager 调用（并发 + 重试）
        task_result = await self.task_manager.run_text2img(final_prompt, task_id)

        # 4. 保存并发送
        image_data = task_result["image_base64"]
        file_path = self._save_temp(image_data)
        yield event.chain_result([
            Plain(result.get("brief_zh", "") + "\n"),
            Image.fromFileSystem(str(file_path))
        ])

        # 5. 清理
        file_path.unlink(missing_ok=True)
```

---

## 十一、注意事项与常见问题

### 10.1 import 路径
- `from astrbot.api.message_components import Image, Plain` 和 `from astrbot.api.all import Image, Plain` 都可
- logger 应从 `astrbot.api` 导入：`from astrbot.api import logger`
- 不要用 `from astrbot import logger`

### 10.2 yield vs await
- Handler 内发消息用 `yield event.plain_result(...)` 或 `yield event.chain_result([...])`
- 钩子函数内（on_llm_request 等）不能用 yield，用 `await event.send(...)`
- 普通异步方法内用 `await`

### 11.3 网络代理
- Gemini API 需要科学上网（国内网络不可直接访问）
- 插件已移除 `proxy_url` 配置项，代理交由系统环境变量处理（`http_proxy`/`https_proxy`）
- 中转站 API 一般不需要代理

### 10.4 token 与密钥
- Gemini API Key 通过 `_conf_schema.json` 配置，不硬编码
- `_conf_schema.json` 中支持 `"ui:password": true` 标记密码字段

### 10.5 插件目录和数据目录
- 插件代码放 `AstrBot/data/plugins/astrbot_plugin_image_gen/`
- 持久化数据放 `data/` 目录下，不要放插件自身目录
- 使用 `StarTools.get_data_dir()` 获取规范路径

### 10.6 依赖声明
- 在 `requirements.txt` 中声明：`httpx`（如果不用 Python 内置的 urllib）
- AstrBot 会自动安装 `requirements.txt` 中的依赖

---

**参考链接**
- AstrBot 插件开发指南：https://docs.astrbot.app/dev/star/plugin-new.html
- Gemini 3.1 Flash Image 文档：https://ai.google.dev/gemini-api/docs/image-generation
- 参考插件：https://github.com/xxuanzQAQ/astrbot_plugin_ai-image
