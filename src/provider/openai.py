# OpenAI 兼容格式 Provider
# 封装 OpenAI /v1/images/generations API（文生图）
# 图生图为试验性支持（/v1/images/edits，多数中转站不支持）

import httpx
from astrbot.api import logger
from .base import ImageProvider


# 尺寸映射表: aspect_ratio → OpenAI 标准分辨率
_SIZE_MAP = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3": "1024x768",
    "3:4": "768x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "4:5": "1024x819",
    "5:4": "819x1024",
    "21:9": "1792x768",
}

# 保底尺寸
_DEFAULT_SIZE = "1024x1024"


class OpenAIProvider(ImageProvider):
    """OpenAI 兼容格式图像生成封装"""

    def __init__(self, api_key: str, api_url: str, model: str, config: dict):
        self.api_key = api_key
        self.api_url = self._normalize_url(api_url)
        self.model = model or "dall-e-3"
        self.timeout = config.get("request_timeout", 120)
        self.image_size = config.get("image_size", "1K")
        self.aspect_ratio = config.get("aspect_ratio", "1:1")

        logger.info(f"OpenAIProvider 初始化: model={self.model}, url={self.api_url}")

    @property
    def supports_img2img(self) -> bool:
        return False

    @staticmethod
    def _normalize_url(url: str) -> str:
        """规范化 API URL，确保指向 images 端点"""
        url = url.rstrip("/")
        # 如果已经是完整路径则直接使用
        if url.endswith("/images/generations"):
            return url
        if url.endswith("/v1"):
            return url + "/images/generations"
        if url.endswith("/v1/"):
            return url + "images/generations"
        # 尝试常见模式
        return url + "/v1/images/generations"

    def _resolve_size(self) -> str:
        """根据 aspect_ratio 和 image_size 确定最终分辨率"""
        return _SIZE_MAP.get(self.aspect_ratio, _DEFAULT_SIZE)

    async def text_to_image(self, prompt: str) -> str:
        """文生图：返回 base64 图片数据"""
        if not self.api_key:
            raise ValueError("API Key 未配置")

        size = self._resolve_size()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        logger.info(f"OpenAI 文生图: model={self.model}, size={size}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.api_url,
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI API 返回错误 ({resp.status_code}): {resp.text[:500]}"
            )

        data = resp.json()
        b64 = data["data"][0]["b64_json"]
        logger.info(f"OpenAI 返回图片: {len(b64)} bytes (base64)")
        return b64

    async def image_to_image(self, prompt: str, reference_base64: str) -> str:
        """图生图（试验性）— 尝试调用 /v1/images/edits

        多数中转站不支持 edits 端点，失败时抛出清晰异常。
        """
        import base64
        from io import BytesIO

        edits_url = self.api_url.replace("/generations", "/edits")

        # 将 base64 解码为 bytes 用于 multipart 上传
        try:
            image_bytes = base64.b64decode(reference_base64)
        except Exception as e:
            raise ValueError(f"参考图片解码失败: {e}")

        files = {
            "image": ("image.png", BytesIO(image_bytes), "image/png"),
            "prompt": (None, prompt),
            "model": (None, self.model),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        logger.info("OpenAI 图生图: 尝试调用 edits 端点")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(edits_url, files=files, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI edits 端点返回错误 ({resp.status_code}): {resp.text[:300]}"
            )

        data = resp.json()
        return data["data"][0]["b64_json"]
