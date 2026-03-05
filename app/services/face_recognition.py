import logging
from typing import List, Tuple, Optional
from pathlib import Path

import numpy as np
import cv2
from insightface.app import FaceAnalysis

from app.core.config import settings

logger = logging.getLogger(__name__)


class FaceRecognitionService:
    """人臉辨識服務 - 使用 InsightFace"""

    def __init__(self):
        self._app: Optional[FaceAnalysis] = None

    def _ensure_loaded(self):
        """確保模型已載入（延遲載入，節省啟動時間）"""
        if self._app is None:
            logger.info("正在載入 InsightFace 模型...")
            self._app = FaceAnalysis(
                name="buffalo_l",  # 使用 buffalo_l 模型（準確度高）
                providers=["CPUExecutionProvider"],  # 使用 CPU（Zeabur 通常沒 GPU）
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace 模型載入完成")

    def detect_faces(self, image_bytes: bytes) -> List[dict]:
        """
        偵測照片中的所有人臉

        Args:
            image_bytes: 照片的二進位資料

        Returns:
            list of dict，每個包含：
            - bbox: [x1, y1, x2, y2] 人臉邊界框
            - embedding: 512 維特徵向量 (numpy array)
            - confidence: 偵測信心度
        """
        self._ensure_loaded()

        # 將 bytes 轉為 OpenCV 格式
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            logger.error("無法解碼圖片")
            return []

        # 執行人臉偵測與特徵提取
        faces = self._app.get(img)

        results = []
        for face in faces:
            results.append({
                "bbox": face.bbox.tolist(),  # [x1, y1, x2, y2]
                "embedding": face.embedding,  # 512 維 numpy array
                "confidence": float(face.det_score),
            })

        logger.info(f"偵測到 {len(results)} 張人臉")
        return results

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        計算兩個人臉特徵向量的餘弦相似度

        Args:
            embedding1: 第一個特徵向量
            embedding2: 第二個特徵向量

        Returns:
            相似度分數 (0-1)，越高表示越像同一人
        """
        # 正規化
        e1 = embedding1 / np.linalg.norm(embedding1)
        e2 = embedding2 / np.linalg.norm(embedding2)
        # 餘弦相似度
        return float(np.dot(e1, e2))


# 全域單例
face_service = FaceRecognitionService()
