# Gemini 3.1 Flash Image Provider
# 封装 Gemini REST API（文生图 + 图生图）

import httpx
from astrbot.api import logger
from .base import ImageProvider


class GeminiProvider(ImageProvider):
    """Gemini 3.1 Flash Image 图像生成/编辑封装"""

    def __init__(self, api_key: str, model: str, config: dict):
        self.api_key = api_key
        self.model = model or "gemini-3.1-flash-image-preview"
        self.timeout = config.get("request_timeout", 120)
        self.aspect_ratio = config.get("aspect_ratio", "1:1")
        self.image_size = config.get("image_size", "1K")

        logger.info(f"GeminiProvider 初始化: model={self.model}")

    @property
    def supports_img2img(self) -> bool:
        return True

    def _build_url(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )

    def _build_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    def _build_config(self) -> dict:
        cfg = {"responseModalities": ["Image", "Text"]}
        image_cfg = {}
        if self.aspect_ratio:
            image_cfg["aspectRatio"] = self.aspect_ratio
        if self.image_size:
            image_cfg["imageSize"] = self.image_size
        if image_cfg:
            cfg["imageConfig"] = image_cfg
        return cfg

    async def text_to_image(self, prompt: str) -> str:
        """文生图：返回 base64 图片数据"""
        if not self.api_key:
            raise ValueError("Gemini API Key 未配置")

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": self._build_config(),
        }
        return await self._call_api(payload)

    @staticmethod
    def _strip_data_uri_prefix(data: str) -> tuple[str, str]:
        """去除 data URI 前缀，返回 (raw_base64, mime_type)"""
        if data and data.startswith("data:"):
            if "," in data:
                header, raw = data.split(",", 1)
                mime = header[5:].split(";")[0]
                return raw, mime
        return data, ""

    async def image_to_image(self, prompt: str, reference_base64: str,
                             mime_type: str = "image/png") -> str:
        """图生图：基于参考图 + 描述编辑"""
        if not self.api_key:
            raise ValueError("Gemini API Key 未配置")

        clean_base64, detected_mime = self._strip_data_uri_prefix(reference_base64)
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": detected_mime or mime_type,
                            "data": clean_base64,
                        }
                    },
                ]
            }],
            "generationConfig": self._build_config(),
        }
        return await self._call_api(payload)

    async def _call_api(self, payload: dict) -> str:
        """调用 Gemini API 并提取图片 base64 数据"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._build_url(),
                json=payload,
                headers=self._build_headers(),
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Gemini API 返回错误 ({resp.status_code}): {resp.text[:500]}"
            )

        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]

        for part in parts:
            if "inline_data" in part:
                logger.info(
                    f"Gemini 返回图片: {part['inline_data']['mime_type']}, "
                    f"{len(part['inline_data']['data'])} bytes (base64)"
                )
                return part["inline_data"]["data"]

        raise RuntimeError("Gemini 响应中未包含图片数据")
