# Prompt Agent 模块
# 负责将用户中文描述改写为适合 Gemini 的英文 prompt

from astrbot.api import logger

# 文生图系统提示词
SYSTEM_PROMPT_T2I = """你是一个图像生成 prompt 工程师。将用户的中文描述改写成适合图像生成模型的英文 prompt。

规则：
1. 输出 JSON 格式：{"final_prompt_en": "...", "brief_zh": "...", "negative_prompt_en": "..."}
2. final_prompt_en 是英文，描述主体、场景、风格、光影、构图、材质细节
3. brief_zh 是中文简述（一句话概括生成内容，用于回传展示）
4. negative_prompt_en 是英文负面 prompt（不希望出现的内容）
5. 只输出 JSON，不要有多余文字

示例：
用户输入："一只机械猫在雨夜的城市中"
输出：{"final_prompt_en": "A cyborg cat with glowing cybernetic eyes sitting on a rain-slicked city street at night, neon signs reflecting in puddles, cinematic lighting, intricate mechanical details, metallic texture, photorealistic, 8K", "brief_zh": "一只机械猫蹲在雨夜的霓虹城市街道上", "negative_prompt_en": "cartoon, anime, low quality, blurry, distorted"}
"""

# 图生图/编辑模式系统提示词
SYSTEM_PROMPT_I2I = """你是一个图像编辑 prompt 工程师。用户会提供一张参考图和修改要求，你需要将修改要求改写成适合图像编辑模型的英文 prompt。

规则：
1. 输出 JSON 格式：{"final_prompt_en": "...", "brief_zh": "...", "negative_prompt_en": "..."}
2. final_prompt_en 是英文，描述需要修改的目标、风格迁移要求、光影/氛围变化
3. brief_zh 是中文简述（一句话概括修改内容）
4. negative_prompt_en 是英文负面 prompt
5. 只输出 JSON，不要有多余文字

示例：
用户输入："把背景换成雪山"
输出：{"final_prompt_en": "Change the background to a majestic snowy mountain landscape with snow-capped peaks, winter atmosphere, cold color temperature, preserving the main subject and foreground composition", "brief_zh": "将背景替换为雪山景观", "negative_prompt_en": "urban, indoor, summer, warm colors"}
"""

MODE_ENHANCED = """补充风格、镜头语言、光影氛围、材质细节，使描述更丰富。"""
MODE_CONSERVATIVE = """尽量不改变用户意图，只做必要的技术性补全。保持简洁。"""
MODE_CREATIVE = """用户输入模糊时可以主动发挥，补充创意细节和艺术表现力。"""


class PromptAgent:
    """调用 AstrBot 已接入的大模型改写 prompt"""

    def __init__(self, context, config: dict):
        self.context = context
        self.mode = config.get("prompt_mode", "enhanced")
        self.style_preset = config.get("style_preset", "auto")
        self.custom_style = config.get("custom_style_prompt", "")
        self._provider_id = None  # 懒加载

    async def _get_provider_id(self) -> str:
        """获取 AstrBot 当前使用的 LLM provider ID"""
        if self._provider_id:
            return self._provider_id
        try:
            # 获取第一个可用的文本生成 provider
            providers = self.context.get_all_providers()
            if providers:
                self._provider_id = providers[0].meta().id
                return self._provider_id
        except Exception as e:
            logger.warning(f"获取 LLM provider 失败: {e}")
        return ""

    async def rewrite(self, user_input: str, mode: str = "text2img") -> dict:
        """将用户输入改写为英文 prompt

        Args:
            user_input: 用户中文描述
            mode: text2img 或 img2img

        Returns:
            {"final_prompt_en": "...", "brief_zh": "...", "negative_prompt_en": "..."}
        """
        # 构建系统提示词
        if mode == "img2img":
            system_prompt = SYSTEM_PROMPT_I2I
        else:
            system_prompt = SYSTEM_PROMPT_T2I

        # 追加模式指令
        if self.mode == "enhanced":
            system_prompt += "\n" + MODE_ENHANCED
        elif self.mode == "conservative":
            system_prompt += "\n" + MODE_CONSERVATIVE
        elif self.mode == "creative":
            system_prompt += "\n" + MODE_CREATIVE

        # 风格预设注入
        style_instruction = self._build_style_instruction()
        if style_instruction:
            system_prompt += f"\n\n当前风格要求：{style_instruction}"

        # 调用 LLM
        try:
            provider_id = await self._get_provider_id()
            if provider_id:
                resp = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=user_input,
                    system_prompt=system_prompt,
                )
                result = self._parse_response(resp.content)
                if result:
                    return result
                logger.warning(f"LLM 返回解析失败，使用原文直出。原始返回: {resp.content[:200]}")
            else:
                logger.warning("无可用 LLM provider，使用降级模式")
        except Exception as e:
            logger.warning(f"LLM 调用失败，使用降级模式: {e}")

        # 降级：原文直出
        return self._fallback(user_input, mode)

    def _build_style_instruction(self) -> str:
        """构建风格指令"""
        parts = []

        # 风格预设映射
        style_map = {
            "realistic": "超写实风格，逼真的光影和纹理",
            "anime": "日式动漫风格，鲜明的线条和色彩",
            "watercolor": "水彩画风格，柔和自然的色彩过渡",
            "cinematic": "电影感风格，宽画幅，电影级光影构图",
            "illustration": "插画风格，干净利落的线条和色块",
            "auto": "",
        }

        preset = style_map.get(self.style_preset, "")
        if preset:
            parts.append(preset)

        if self.custom_style:
            parts.append(self.custom_style)

        return "，".join(parts) if parts else ""

    def _parse_response(self, text: str) -> dict | None:
        """解析 LLM 返回的 JSON"""
        import json
        import re

        # 尝试提取 JSON 块
        match = re.search(r'\{.*"final_prompt_en".*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if data.get("final_prompt_en"):
                    return {
                        "final_prompt_en": data["final_prompt_en"],
                        "brief_zh": data.get("brief_zh", ""),
                        "negative_prompt_en": data.get("negative_prompt_en", ""),
                    }
            except json.JSONDecodeError:
                pass
        return None

    def _fallback(self, user_input: str, mode: str = "text2img") -> dict:
        """降级方案：原文直出"""
        logger.info(f"PromptAgent 降级模式，原文: {user_input[:50]}")
        return {
            "final_prompt_en": user_input,
            "brief_zh": user_input,
            "negative_prompt_en": "",
        }
