# Image Provider 抽象基类
# 定义所有图像生成 provider 的统一接口

from abc import ABC, abstractmethod


class ImageProvider(ABC):
    """图像生成 provider 抽象基类"""

    @abstractmethod
    async def text_to_image(self, prompt: str) -> str:
        """文生图：返回 base64 图片数据"""
        ...

    async def image_to_image(self, prompt: str, reference_base64: str) -> str:
        """图生图：基于参考图 + 描述编辑，返回 base64 图片数据

        默认抛出 NotImplementedError，子类若支持则覆盖。
        """
        raise NotImplementedError("当前 Provider 不支持图生图")

    @property
    def supports_img2img(self) -> bool:
        """是否支持图生图"""
        return False
