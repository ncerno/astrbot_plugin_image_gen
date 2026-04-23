# 文生图插件项目规范

## 项目目标
本项目用于开发 AstrBot 的图片生成插件，目标场景为 QQ 私聊与群聊中的文生图、图生图能力。
当前阶段仅允许做两件事：
1. 建立项目规则
2. 搭建基础目录骨架

未确认 AstrBot 官方接口、Gemini 图像接口、QQ 发图链路前，不开始功能开发。

## 目录规范
项目根目录固定采用以下结构：

- `docs/`：方案书、接口调研、补充说明
- `src/`：源码根目录
- `src/plugin/`：AstrBot 插件入口、消息监听、命令路由
- `src/prompt/`：prompt 改写与提示词策略
- `src/provider/`：图像服务 provider 封装
- `src/task/`：异步任务提交、轮询、重试
- `src/storage/`：任务状态与轻量持久化
- `src/temp/`：临时图片与短期缓存文件
- `tests/`：测试与验证入口

新增目录或文件前，先判断是否能放入现有结构；能复用就不新增。
临时文件只允许放在 `src/temp/`，生成完成后应清理。
文档优先放 `docs/`，不要把说明散落在根目录。

## 命名约定
- 目录名、文件名默认使用英文小写
- 多词文件名使用 snake_case 或与所选语言的主流约定保持一致
- 配置项名称保持可读、直接，不做无意义缩写

## 开发纪律
- 开发前先读取本文件，再动手
- 大改动前先进入 Plan Mode，确认后再实施
- 改规范时，先改 `CLAUDE.md`，再改实际结构或代码
- 不为了跑通而注释报错、绕过校验或加入临时 hack
- 改完必须做验证，验证命令以后写入本文件
- 密钥、token、密码不进代码、不进提交、不进日志

## 接口确认记录（已确认，2026-04-23）

以下接口已通过官方文档和参考插件源码（`astrbot_plugin_ai-image`、`astrbot_plugin_gemini_artist`）验证。

### AstrBot 插件注册
```python
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

@register("plugin_name", "Author", "描述", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
```

- `metadata.yaml` 必填，字段：`name`, `desc`, `version`, `author`, `repo`
- 插件类必须放在 `main.py`
- 可选的 `async def initialize(self)` 和 `async def terminate(self)`

### 命令注册
```python
@filter.command("draw")
async def draw(self, event: AstrMessageEvent, prompt: str = ""): ...
```
- 命令参数会自动解析，`@filter.command("add")` 匹配 `/add 1 2`
- 支持类型注解（`a: int`, `b: str` 等）

### 消息事件监听（非命令）
```python
async def on_message(self, event: AstrMessageEvent): ...       # 所有消息
async def on_private_message(self, event: AstrMessageEvent): ... # 私聊
async def on_all_message(self, event: AstrMessageEvent): ...    # 群聊+私聊
```

### 图片发送
```python
from astrbot.api.message_components import Image, Plain
from astrbot.api.all import Image, Plain  # 或从 all 导入

# 方式1：文件路径
yield event.chain_result([Plain("描述"), Image.fromFileSystem("path/to/image.jpg")])
# 方式2：URL
yield event.chain_result([Plain("描述"), Image.fromURL("https://example.com/image.jpg")])
# 方式3：纯文本
yield event.plain_result("Hello!")
```

### 图片读取（从用户消息中提取）
```python
for comp in event.message_obj.message:
    if isinstance(comp, Image):
        base64_data = await comp.convert_to_base64()  # 转为 base64
```
- 也支持从回复消息中提取：`Reply.chain` 遍历

### 插件配置
- 插件目录下放 `_conf_schema.json` 定义配置 schema
- 配置实体保存在 `data/config/<plugin_name>_config.json`
- `config: dict` 通过 `__init__` 注入
- 访问其他配置：`self.context.get_config()`

### 消息链组件
```python
import astrbot.api.message_components as Comp
Comp.Plain("text")                      # 纯文本
Comp.Image.fromFileSystem("path")       # 图片（文件）
Comp.Image.fromURL("url")               # 图片（URL）
Comp.At(qq=event.get_sender_id())       # @某人
Comp.Reply()                            # 回复消息
Comp.Video.fromFileSystem(path)         # 视频
Comp.Video.fromURL(url)                 # 视频（URL）
Comp.Record(file=path, url=url)         # 语音
Comp.File(file=path)                    # 文件
Comp.Node(users=[], content=[])         # 合并转发节点
```

### Gemini 3.1 Flash Image API
```
模型:      gemini-3.1-flash-image-preview
端点:      POST .../v1beta/models/gemini-3.1-flash-image-preview:generateContent
认证:      x-goog-api-key header
输入token: 131,072 | 输出token: 32,768
定价:      $0.25/1M tokens (text input) / $0.067 per image output
Temp:      0.0–2.0 (default 1.0)
不支持:    function calling、caching、code execution
```

**文生图请求**：contents 中放 text prompt
**图生图请求**：contents 中 text + inline_data（参考图 base64）
**响应**：`candidates[0].content.parts[]`，每个 part 可能是 `text` 或 `inline_data`（图片 base64）

可选配置：
- `response_modalities`: `['Image']` 或 `['Text', 'Image']`
- `image_config.aspect_ratio`: 1:1, 16:9, 4:3, 3:2, 3:4, 4:5, 5:4, 9:16, 21:9, 1:4, 4:1, 1:8, 8:1, 2:3
- `image_config.image_size`: 512, 1K, 2K, 4K
- Thinking 默认开启，不可关闭

### AstrBot 调用 LLM（用于 prompt 改写）
```python
from astrbot.api.provider import ProviderRequest
# 通过事件钩子 on_llm_request 可获取 ProviderRequest 对象
```

### 各模块工具
- 文件下载：`from astrbot.core.utils.io import download_file`
- 数据目录：`StarTools.get_data_dir()`（从 `astrbot.api.star` 导入 StarTools）

## 默认实施顺序
1. 搭骨架（metadata.yaml + main.py 空插件 + 目录结构）
2. 做配置模块（_conf_schema.json + AstrBotConfig）
3. 做 Gemini provider 封装（调用 Gemini API 文生图）
4. 做消息路由（命令触发 + 聊天触发）
5. 做 Prompt Agent（调 LLM 改写中文→英文 prompt）
6. 做文生图 MVP（链路打通）
7. 补图生图（图片提取 + Gemini 编辑）
8. 做临时文件管理
9. 完善重试/错误处理/日志

## 验证命令
- `python -c "import astrbot; print('ok')"` — 检查 astrbot 依赖
- 运行 AstrBot 本体后，在 QQ 中发送 `/draw xxx` 验证
