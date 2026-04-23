# 任务管理模块
# Gemini API 是同步接口，此模块提供并发控制和重试逻辑

import asyncio
import time
from astrbot.api import logger


class TaskManager:
    """任务调度与并发控制"""

    def __init__(self, config: dict, provider, task_store):
        self.provider = provider
        self.task_store = task_store
        self.max_retry = config.get("max_retry", 2)
        self.global_semaphore = asyncio.Semaphore(
            config.get("global_concurrency", 3)
        )

    async def run_text2img(self, prompt: str, task_id: str = "") -> dict:
        """执行文生图任务（含重试）"""
        self.task_store.update(task_id, status="running")

        async with self.global_semaphore:
            last_error = None
            for attempt in range(1 + self.max_retry):
                try:
                    image_data = await self.provider.text_to_image(prompt)
                    self.task_store.update(task_id, status="success")
                    return {"image_base64": image_data, "success": True}
                except Exception as e:
                    last_error = e
                    logger.warning(f"文生图失败 (第{attempt+1}次): {e}")
                    if attempt < self.max_retry:
                        await asyncio.sleep(2 ** attempt)  # 退避

        self.task_store.update(task_id, status="failed", error=str(last_error))
        return {"success": False, "error": str(last_error)}

    async def run_img2img(self, prompt: str, reference_base64: str,
                          task_id: str = "") -> dict:
        """执行图生图任务（含重试）"""
        self.task_store.update(task_id, status="running")

        async with self.global_semaphore:
            last_error = None
            for attempt in range(1 + self.max_retry):
                try:
                    image_data = await self.provider.image_to_image(
                        prompt, reference_base64
                    )
                    self.task_store.update(task_id, status="success")
                    return {"image_base64": image_data, "success": True}
                except Exception as e:
                    last_error = e
                    logger.warning(f"图生图失败 (第{attempt+1}次): {e}")
                    if attempt < self.max_retry:
                        await asyncio.sleep(2 ** attempt)

        self.task_store.update(task_id, status="failed", error=str(last_error))
        return {"success": False, "error": str(last_error)}

    def get_active_count(self) -> int:
        """当前活跃任务数"""
        return self.global_semaphore._value
