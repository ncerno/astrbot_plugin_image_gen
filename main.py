from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

from src.prompt.agent import PromptAgent
from src.provider.gemini import GeminiProvider
from src.provider.openai import OpenAIProvider
from src.provider.base import ImageProvider
from src.storage.state import TaskStore
from src.task.manager import TaskManager

import asyncio
from pathlib import Path
import uuid
from datetime import datetime


@register(
    "astrbot_plugin_image_gen",
    "nero",
    "基于 Gemini / OpenAI 兼容 API 的文生图/图生图插件",
    "0.2.0",
)
class ImageGenPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        # 路径配置
        self.temp_dir = Path("src/temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 解析 Provider
        self.provider: ImageProvider | None = None
        try:
            self.provider = self._resolve_provider(context, config)
        except Exception as e:
            logger.error(f"初始化图像 Provider 失败: {e}")

        # 模块初始化
        self.prompt_agent = PromptAgent(context, config)
        self.task_store = TaskStore()
        self.task_manager = TaskManager(config, self.provider, self.task_store)

        # 配置值缓存
        self.draw_cmd = config.get("draw_command", "draw")
        self.imgedit_cmd = config.get("imgedit_command", "imgedit")
        self.drawraw_cmd = config.get("drawraw_command", "drawraw")
        self.delete_temp = config.get("delete_temp_after_send", True)
        self.show_final_prompt = config.get("show_final_prompt", False)

        if self.provider:
            logger.info(
                f"图片生成插件已加载: {type(self.provider).__name__}, "
                f"模型: {config.get('model', '')}"
            )
        else:
            logger.warning("图片生成插件已加载，但未配置 Provider")

    # ── Provider 解析 ──────────────────────────────────

    def _resolve_provider(self, context: Context, config: dict) -> ImageProvider | None:
        """解析图像生成 Provider

        优先级：
        1. _special: select_provider → 用户选定的 AstrBot provider
        2. 自动发现 → 第一个有 API Key 的 provider
        3. 备用手动配置 fallback_*
        """
        provider_id = config.get("provider_id", "")
        model = config.get("model", "gemini-3.1-flash-image-preview")
        api_key = ""
        api_url = ""

        # ── 从 AstrBot provider 获取 ──
        api_key, api_url, is_gemini = self._discover_from_astrbot(
            context, provider_id
        )

        # ── 手动 URL 覆盖 ──
        manual_url = config.get("provider_endpoint_url", "").strip()
        if manual_url:
            api_url = manual_url

        # ── 若自动发现成功，构建 provider ──
        if api_key:
            return self._build_provider(api_key, api_url, model, config, is_gemini)

        # ── 备用手动配置 ──
        fallback_key = config.get("fallback_api_key", "").strip()
        fallback_url = config.get("fallback_api_url", "").strip()
        fallback_model = config.get("fallback_model", "").strip()

        if fallback_key and fallback_url:
            fb_model = fallback_model or model
            fb_is_gemini = "google" in fallback_url.lower() or "gemini" in fallback_url.lower()
            return self._build_provider(fallback_key, fallback_url, fb_model, config, fb_is_gemini)

        logger.warning(
            "无法初始化图像生成 Provider。请在管理面板中："
            "① 配置模型提供商并通过 provider_id 选择；"
            "② 或在备用配置中填写 API Key 和 URL。"
        )
        return None

    def _discover_from_astrbot(self, context: Context,
                                target_id: str) -> tuple[str, str, bool]:
        """从 AstrBot providers 发现 API Key 和类型

        Returns:
            (api_key, api_url, is_gemini)
        """
        try:
            providers = context.get_all_providers()
            for p in providers:
                meta = p.meta()
                if target_id and meta.id != target_id:
                    continue

                keys = p.get_keys()
                if not keys or not keys[0]:
                    continue

                api_key = keys[0]
                type_name = (meta.type or "").lower()
                is_gemini = "gemini" in type_name or "google" in type_name

                # 获取 base URL（仅非 Gemini 需要）
                api_url = ""
                if not is_gemini:
                    api_url = (
                        getattr(p, "base_url", None)
                        or getattr(p, "api_base", None)
                        or ""
                    )

                provider_label = meta.id or meta.model or "unknown"
                logger.info(
                    f"从 AstrBot provider '{provider_label}' 获取配置: "
                    f"{'Gemini' if is_gemini else 'OpenAI兼容'}"
                )
                return api_key, api_url, is_gemini

        except Exception as e:
            logger.warning(f"从 AstrBot 自动获取 provider 失败: {e}")

        return "", "", False

    @staticmethod
    def _build_provider(api_key: str, api_url: str, model: str,
                        config: dict, is_gemini: bool) -> ImageProvider:
        """根据类型构建 provider 实例"""
        if is_gemini:
            return GeminiProvider(api_key, model, config)
        else:
            return OpenAIProvider(api_key, api_url, model, config)

    # ── 消息路由（## 命令） ──────────────────────────────

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

    # ── 消息路由（## 命令） ──────────────────────────────

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

    # ── 核心处理流程 ──────────────────────────────────

    def _check_provider(self, event: AstrMessageEvent):
        """检查 provider 是否可用"""
        if not self.provider:
            return event.plain_result(
                "插件未配置：请在管理面板中配置模型提供商（provider_id），"
                "或填写备用 API Key 和 URL。"
            )
        return None

    async def _handle_text2img(self, event: AstrMessageEvent, prompt: str,
                                skip_prompt_agent: bool = False):
        """文生图流程"""
        err = self._check_provider(event)
        if err:
            yield err
            return

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

            # 2. 通过 TaskManager 调用
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
        err = self._check_provider(event)
        if err:
            yield err
            return

        # 1. 检查 provider 是否支持图生图
        if not self.provider.supports_img2img:
            yield event.plain_result(
                "当前模型不支持图生图功能。请使用 Gemini 模型，"
                "或切换到文生图模式（##draw）。"
            )
            return

        # 2. 从消息中提取图片
        image_base64 = await self._extract_image(event)
        if not image_base64:
            yield event.plain_result("请同时发送一张参考图片（仅支持 JPG/PNG，大小 < 10MB）")
            return

        yield event.plain_result("正在处理图片编辑，请稍候……")

        try:
            # 3. Prompt 改写
            result = await self.prompt_agent.rewrite(prompt, mode="img2img")
            final_prompt = result["final_prompt_en"]
            brief_zh = result.get("brief_zh", "")

            logger.info(f"图生图 | prompt: {final_prompt[:100]}")

            # 4. 通过 TaskManager 调用
            task_id = uuid.uuid4().hex
            self.task_store.create(task_id, {"user_id": event.get_sender_id()})
            task_result = await self.task_manager.run_img2img(final_prompt, image_base64, task_id)

            if not task_result["success"]:
                yield event.plain_result(f"编辑失败: {task_result.get('error', '未知错误')}")
                return

            image_data = task_result["image_base64"]

            # 5. 保存临时文件
            file_path = self._save_temp(image_data)

            # 6. 构建返回消息
            reply_parts = []
            if brief_zh:
                reply_parts.append(Plain(brief_zh + "\n"))
            if self.show_final_prompt:
                reply_parts.append(Plain(f"[Prompt] {final_prompt}\n"))
            reply_parts.append(Image.fromFileSystem(str(file_path)))

            yield event.chain_result(reply_parts)

            # 7. 清理
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
