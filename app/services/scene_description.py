import base64
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """取得 OpenAI 客戶端（延遲初始化）"""
    global client
    if client is None:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    return client


async def describe_scene(image_bytes: bytes, recognized_names: list[str] = None) -> Optional[str]:
    """
    使用 GPT-4o 分析照片場景，產生場景描述

    Args:
        image_bytes: 照片的二進位資料
        recognized_names: 已辨識出的人名列表（提供上下文）

    Returns:
        場景描述文字，失敗時回傳 None
    """
    if not settings.openai_api_key:
        logger.warning("未設定 OpenAI API Key，跳過場景描述")
        return None

    try:
        openai_client = get_openai_client()

        # 將圖片轉為 base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # 建構 prompt
        names_context = ""
        if recognized_names:
            names_str = "、".join(recognized_names)
            names_context = f"\n照片中辨識到的人：{names_str}"

        prompt = f"""請用繁體中文簡短描述這張照片的場景。包含以下資訊：
- 場所類型（例如：咖啡廳、餐廳、戶外公園等）
- 大致氛圍（例如：輕鬆聚餐、正式聚會、戶外活動等）
- 特殊細節（例如：慶生、節日、特殊裝飾等）
{names_context}

請用 1-2 句話簡潔描述，不要超過 50 字。直接描述場景，不要加任何前綴。"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low",  # 使用 low detail 節省成本
                            },
                        },
                    ],
                }
            ],
            max_tokens=150,
            temperature=0.3,
        )

        description = response.choices[0].message.content.strip()
        logger.info(f"AI 場景描述：{description}")
        return description

    except Exception as e:
        logger.error(f"GPT-4o 場景描述失敗：{e}")
        return None
