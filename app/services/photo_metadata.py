import logging
from datetime import datetime
from typing import Optional, Tuple
from io import BytesIO

import exifread

logger = logging.getLogger(__name__)


def _convert_to_degrees(value) -> float:
    """將 EXIF GPS 座標轉為十進位度數"""
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)


def extract_photo_time(image_bytes: bytes) -> Optional[datetime]:
    """
    從照片 EXIF 中提取拍攝時間

    Args:
        image_bytes: 照片二進位資料

    Returns:
        拍攝時間，無法提取時回傳 None
    """
    try:
        tags = exifread.process_file(BytesIO(image_bytes), details=False)

        # 嘗試多個可能的時間標籤
        time_tags = [
            "EXIF DateTimeOriginal",
            "EXIF DateTimeDigitized",
            "Image DateTime",
        ]

        for tag_name in time_tags:
            if tag_name in tags:
                time_str = str(tags[tag_name])
                # EXIF 時間格式：2024:01:15 14:30:00
                try:
                    return datetime.strptime(time_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue

    except Exception as e:
        logger.warning(f"提取照片時間失敗：{e}")

    return None


def extract_photo_location(image_bytes: bytes) -> Optional[Tuple[float, float]]:
    """
    從照片 EXIF 中提取 GPS 座標

    Args:
        image_bytes: 照片二進位資料

    Returns:
        (緯度, 經度) 元組，無法提取時回傳 None
    """
    try:
        tags = exifread.process_file(BytesIO(image_bytes), details=False)

        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lng_tag = tags.get("GPS GPSLongitude")
        lng_ref = tags.get("GPS GPSLongitudeRef")

        if not all([lat_tag, lat_ref, lng_tag, lng_ref]):
            return None

        lat = _convert_to_degrees(lat_tag)
        lng = _convert_to_degrees(lng_tag)

        # 南緯和西經為負值
        if str(lat_ref) == "S":
            lat = -lat
        if str(lng_ref) == "W":
            lng = -lng

        return (lat, lng)

    except Exception as e:
        logger.warning(f"提取照片 GPS 失敗：{e}")

    return None
