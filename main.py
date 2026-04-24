from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

from src.prompt.agent import PromptAgent
from src.provider.gemini import GeminiProvider
from src.storage.state import TaskStore
from src.task.manager import TaskManager

import asyncio
from pathlib import Path
import uuid
from datetime import datetime


@register(
    "astrbot_plugin_image_gen",
    "nero",
    "基于 Gemini 3.1 Flash Image 的文生图/图生图插件",
    "0.1.0",
)
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        # 路径配置
        self.temp_dir = Path("src/temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 模块初始化
        self.provider = GeminiProvider(config, context=context)
        self.prompt_agent = PromptAgent(context, config)
        self.task_store = TaskStore()
        self.task_manager = TaskManager(config, self.provider, self.task_store)

        # 配置值缓存
        self.enable_chat_trigger = config.get("enable_chat_trigger", True)
        self.chat_trigger_t2i = config.get("chat_trigger_text2img", "帮我画")
        self.chat_trigger_i2i = config.get("chat_trigger_img2img", "帮我改图")
        self.draw_command = config.get("draw_command", "draw")
        self.imgedit_command = config.get("imgedit_command", "imgedit")
        self.drawraw_command = config.get("drawraw_command", "drawraw")
        self.delete_temp = config.get("delete_temp_after_send", True)
        self.show_final_prompt = config.get("show_final_prompt", False)

        logger.info(f"图片生成插件已加载，模型: {config.get('model', 'gemini-3.1-flash-image-preview')}")

    async def initialize(self):
        """插件初始化——启动定时清理任务"""
        interval = self.config.get("cleanup_interval_minutes", 30)
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup(interval))
        logger.info("图片生成插件初始化完成")

    async def terminate(self):
        """插件卸载时清理"""
        if hasattr(self, "_cleanup_task"):
            self._cleanup_task.cancel()
        self._cleanup_temp()
        logger.info("图片生成插件已卸载")

    # ── 命令路由 ──────────────────────────────────────

    @filter.command("draw")
    async def draw(self, event: AstrMessageEvent, prompt: str = ""):
        """文生图：/draw <描述>"""
        if not prompt:
            yield event.plain_result(f"用法：/{self.draw_command} <图片描述>")
            return
        async for result in self._handle_text2img(event, prompt):
            yield result

    @filter.command("imgedit")
    async def imgedit(self, event: AstrMessageEvent, prompt: str = ""):
        """图生图：/imgedit <修改描述>（需同时发送参考图）"""
        if not prompt:
            yield event.plain_result(f"用法：/{self.imgedit_command} <修改描述>（需同时发送参考图片）")
            return
        async for result in self._handle_img2img(event, prompt):
            yield result

    @filter.command("drawraw")
    async def drawraw(self, event: AstrMessageEvent, prompt: str = ""):
        """跳过 LLM 扩写，直接提交 Gemini 生图"""
        if not prompt:
            yield event.plain_result(f"用法：/{self.drawraw_command} <英文 prompt>")
            return
        async for result in self._handle_text2img(event, prompt, skip_prompt_agent=True):
            yield result

    # ── 聊天触发 ──────────────────────────────────────

    async def on_message(self, event: AstrMessageEvent):
        """监听普通消息，检测聊天触发词"""
        if not self.enable_chat_trigger:
            return

        text = event.message_str.strip()

        # 文生图触发
        if text.startswith(self.chat_trigger_t2i):
            prompt = text[len(self.chat_trigger_t2i):].strip()
            if prompt:
                async for result in self._handle_text2img(event, prompt):
                    yield result
            return

        # 图生图触发
        if text.startswith(self.chat_trigger_i2i):
            prompt = text[len(self.chat_trigger_i2i):].strip()
            if prompt:
                async for result in self._handle_img2img(event, prompt):
                    yield result
            return

    # ── 核心处理流程 ──────────────────────────────────

    async def _handle_text2img(self, event: AstrMessageEvent, prompt: str, skip_prompt_agent: bool = False):
        """文生图流程"""
        yield event.plain_result("正在生成图片，请稍候……")

        try:
            # 1. Prompt 改写
            if skip_prompt_agent:
                final_prompt = prompt
                brief_zh = ""
            else:
                result = await self.prompt_agent.rewrite(prompt, mode="text2img")
                final_prompt = result["final_prompt_en"]
                brief_zh = result.get("brief_zh", "")

            logger.info(f"文生图 | prompt: {final_prompt[:100]}")

            # 2. 通过 TaskManager 调用（含并发控制 + 自动重试）
            task_id = uuid.uuid4().hex
            self.task_store.create(task_id, {"user_id": event.get_sender_id()})
            task_result = await self.task_manager.run_text2img(final_prompt, task_id)

            if not task_result["success"]:
                yield event.plain_result(f"生成失败: {task_result.get('error', '未知错误')}")
                return

            image_data = task_result["image_base64"]

            # 3. 保存临时文件
            file_path = self._save_temp(image_data)

            # 4. 构建返回消息
            reply_parts = []
            if brief_zh:
                reply_parts.append(Plain(brief_zh + "\n"))
            if self.show_final_prompt:
                reply_parts.append(Plain(f"[Prompt] {final_prompt}\n"))
            reply_parts.append(Image.fromFileSystem(str(file_path)))

            yield event.chain_result(reply_parts)

            # 5. 清理
            if self.delete_temp:
                file_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"文生图失败: {e}")
            yield event.plain_result(f"生成失败: {str(e)}")

    async def _handle_img2img(self, event: AstrMessageEvent, prompt: str):
        """图生图流程"""
        # 1. 从消息中提取图片
        image_base64 = await self._extract_image(event)
        if not image_base64:
            yield event.plain_result("请同时发送一张参考图片")
            return

        yield event.plain_result("正在处理图片编辑，请稍候……")

        try:
            # 2. Prompt 改写
            result = await self.prompt_agent.rewrite(prompt, mode="img2img")
            final_prompt = result["final_prompt_en"]
            brief_zh = result.get("brief_zh", "")

            logger.info(f"图生图 | prompt: {final_prompt[:100]}")

            # 3. 通过 TaskManager 调用（含并发控制 + 自动重试）
            task_id = uuid.uuid4().hex
            self.task_store.create(task_id, {"user_id": event.get_sender_id()})
            task_result = await self.task_manager.run_img2img(final_prompt, image_base64, task_id)

            if not task_result["success"]:
                yield event.plain_result(f"编辑失败: {task_result.get('error', '未知错误')}")
                return

            image_data = task_result["image_base64"]

            # 4. 保存临时文件
            file_path = self._save_temp(image_data)

            # 5. 构建返回消息
            reply_parts = []
            if brief_zh:
                reply_parts.append(Plain(brief_zh + "\n"))
            if self.show_final_prompt:
                reply_parts.append(Plain(f"[Prompt] {final_prompt}\n"))
            reply_parts.append(Image.fromFileSystem(str(file_path)))

            yield event.chain_result(reply_parts)

            # 6. 清理
            if self.delete_temp:
                file_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"图生图失败: {e}")
            yield event.plain_result(f"编辑失败: {str(e)}")

    # ── 工具方法 ──────────────────────────────────────

    async def _extract_image(self, event: AstrMessageEvent):
        """从用户消息中提取第一张图片的 base64"""
        if not hasattr(event, "message_obj") or not event.message_obj:
            return None
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                try:
                    return await comp.convert_to_base64()
                except Exception as e:
                    logger.warning(f"读取图片失败: {e}")
        return None

    @staticmethod
    def _strip_data_uri_prefix(data: str) -> str:
        if data and data.startswith("data:"):
            if "," in data:
                return data.split(",", 1)[1]
        return data

    def _save_temp(self, image_base64: str) -> Path:
        """将 base64 图片保存到临时目录"""
        import base64
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        file_path = self.temp_dir / f"gen_{ts}_{uid}.png"
        data = base64.b64decode(self._strip_data_uri_prefix(image_base64))
        file_path.write_bytes(data)
        return file_path

    def _cleanup_temp(self):
        """清理所有临时文件"""
        for f in self.temp_dir.glob("gen_*.png"):
            f.unlink(missing_ok=True)

    async def _periodic_cleanup(self, interval_minutes: int):
        """定时清理过期残留文件"""
        while True:
            await asyncio.sleep(interval_minutes * 60)
            now = datetime.now()
            cutoff = now.timestamp() - interval_minutes * 60
            for f in self.temp_dir.glob("gen_*.png"):
                if f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
                    logger.debug(f"清理过期文件: {f}")
