# AstrBot × Gemini 3.1 Flash Image 插件开发技术参考

> 基于官方文档与参考插件源码整理，版本确认日期：2026-04-23

---

## 目录结构

```
astrbot_plugin_image_gen/
├── main.py                    # 插件入口（必须叫 main.py）
├── metadata.yaml              # 插件元数据（必填）
├── _conf_schema.json          # 配置 schema（可选，推荐）
├── requirements.txt           # pip 依赖
├── logo.png                   # 插件图标（可选）
│
├── prompt/
│   ├── __init__.py
│   └── agent.py               # Prompt Agent 模块
├── provider/
│   ├── __init__.py
│   └── gemini.py              # Gemini 3.1 Flash Image 封装
├── task/
│   ├── __init__.py
│   └── manager.py             # 异步任务管理
├── storage/
│   ├── __init__.py
│   └── state.py               # 任务状态持久化
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

@register(
    "astrbot_plugin_image_gen",     # 插件名
    "AuthorName",                    # 作者
    "基于 Gemini 3.1 Flash Image 的文生图/图生图插件",  # 描述
    "0.1.0"                         # 版本
)
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # config 来自 _conf_schema.json 定义的配置项，已被框架自动加载
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-3.1-flash-image-preview")
        # ... 其他配置

    async def initialize(self):
        """可选的异步初始化方法，实例化后自动调用"""
        logger.info("图片生成插件已加载")

    async def terminate(self):
        """可选的销毁方法，插件被卸载/停用时调用"""
        logger.info("图片生成插件已卸载")
```

---

## 二、消息处理

### 2.1 命令注册

使用 `@filter.command("name")` 装饰器注册命令。

```python
@filter.command("draw")
async def draw(self, event: AstrMessageEvent, prompt: str = ""):
    """文生图命令：/draw <描述>"""
    if not prompt:
        yield event.plain_result("请提供图片描述，例如：/draw 一只猫")
        return
    yield event.plain_result(f"正在生成: {prompt}")
    # ... 调用生成逻辑
```

**参数自动解析规则**：

| 命令 | 用户输入 | handler 参数 |
|------|----------|-------------|
| `@filter.command("echo")` | `/echo hello world` | `self, event, message: str` → message="hello world" |
| `@filter.command("add")` | `/add 3 5` | `self, event, a: int, b: int` → a=3, b=5 |
| `@filter.command("draw")` | `/draw` | `self, event, prompt: str = ""` → prompt="" |

支持类型注解自动转换：`int`, `float`, `str`, `bool`。

### 2.2 聊天触发（非命令消息监听）

```python
async def on_message(self, event: AstrMessageEvent):
    """监听所有消息"""
    text = event.message_str
    if "帮我画" in text:
        # 提取描述内容
        prompt = text.replace("帮我画", "").strip()
        yield event.plain_result(f"收到，正在生成: {prompt}")
        # ... 调用生成逻辑

async def on_private_message(self, event: AstrMessageEvent):
    """仅私聊消息"""
    pass

async def on_all_message(self, event: AstrMessageEvent):
    """群聊+私聊（比 on_message 覆盖更广）"""
    pass
```

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
    "model": {
      "type": "string",
      "description": "Gemini 图像模型名称",
      "default": "gemini-3.1-flash-image-preview",
      "hint": "gemini-3.1-flash-image-preview / gemini-3-pro-image-preview"
    },
    "style_preset": {
      "type": "string",
      "description": "风格预设：auto / realistic / anime / watercolor / cinematic / illustration",
      "default": "auto"
    },
    "prompt_mode": {
      "type": "string",
      "description": "Prompt 改写模式：conservative / enhanced / creative",
      "default": "enhanced"
    },
    "proxy_url": {
      "type": "string",
      "description": "代理地址",
      "default": ""
    }
  }
}
```

> 注意：插件已移除 `api_key` 配置项。API Key 通过 AstrBot 的 Google Gemini 模型提供商自动获取，无需在插件中重复配置。

### 5.2 API Key 自动发现机制

本插件已移除独立的 `api_key` 配置项。`GeminiProvider` 在初始化时自动从 AstrBot 已配置的 provider 中查找 Google/Gemini 类型的提供商并提取 API Key。

```python
class GeminiProvider:
    def __init__(self, config: dict, context=None):
        # 优先从插件配置读取（兼容旧配置）
        self.api_key = config.get("api_key", "")

        # 未配置时从 AstrBot provider 自动发现
        if not self.api_key and context:
            self.api_key = self._discover_api_key(context)

    @staticmethod
    def _discover_api_key(context) -> str:
        """从 AstrBot 已配置的 provider 中自动发现 Gemini API Key"""
        providers = context.get_all_providers()
        for provider in providers:
            meta = provider.meta()
            type_name = (meta.type or "").lower()
            if "gemini" in type_name or "google" in type_name:
                keys = provider.get_keys()
                if keys and keys[0]:
                    return keys[0]
        return ""
```

**配置策略：**
- 用户只需在 AstrBot 管理面板添加 Google Gemini 模型提供商并填入 API Key
- 插件自动发现并使用该 Key
- 旧部署的插件配置中若仍有 `api_key`，会优先使用，不会断掉

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

## 六、Gemini 3.1 Flash Image API

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

## 七、参考插件模式

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

## 八、临时文件管理

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

## 九、完整的命令 Handler 示例

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain
from astrbot.api.all import Image as AllImage, Plain as AllPlain

import httpx
import base64
from pathlib import Path

@register("astrbot_plugin_image_gen", "Author", "图片生成插件", "0.1.0")
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-3.1-flash-image-preview")
        self.temp_dir = Path("src/temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @filter.command("draw")
    async def draw(self, event: AstrMessageEvent, prompt: str = ""):
        """文生图：/draw <描述>"""
        if not prompt:
            yield event.plain_result("用法：/draw <图片描述>")
            return

        yield event.plain_result(f"正在生成: {prompt}")

        try:
            # 调用 Gemini API 生图
            image_data = await self._call_gemini(prompt)

            # 保存到临时文件
            file_path = self.temp_dir / f"gen_{uuid.uuid4().hex[:8]}.png"
            base64.b64decode(image_data)
            # ... 实际保存

            # 发送结果
            yield event.chain_result([
                Plain("生成完成！"),
                Image.fromFileSystem(str(file_path))
            ])

            # 清理
            file_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"生图失败: {e}")
            yield event.plain_result(f"生成失败: {str(e)}")

    async def _call_gemini(self, prompt: str) -> str:
        """调用 Gemini API 返回 base64 图片数据"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["Image"],
            },
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=120)
        data = resp.json()
        for part in data["candidates"][0]["content"]["parts"]:
            if "inline_data" in part:
                return part["inline_data"]["data"]
        raise Exception("No image in response")
```

---

## 十、注意事项与常见问题

### 10.1 import 路径
- `from astrbot.api.message_components import Image, Plain` 和 `from astrbot.api.all import Image, Plain` 都可
- logger 应从 `astrbot.api` 导入：`from astrbot.api import logger`
- 不要用 `from astrbot import logger`

### 10.2 yield vs await
- Handler 内发消息用 `yield event.plain_result(...)` 或 `yield event.chain_result([...])`
- 钩子函数内（on_llm_request 等）不能用 yield，用 `await event.send(...)`
- 普通异步方法内用 `await`

### 10.3 网络代理
- Gemini API 需要科学上网（国内网络不可直接访问）
- 建议将代理配置交给 AstrBot 全局配置或插件配置项
- 参考 `astrbot_plugin_ai-image` 中的 `should_use_proxy()` 函数判断是否需要代理

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
