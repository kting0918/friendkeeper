import logging
from typing import List, Optional

import numpy as np
import cv2
import face_recognition as fr

logger = logging.getLogger(__name__)


class FaceRecognitionService:
    """人臉辨識服務 - 使用 face_recognition (dlib)"""

    def detect_faces(self, image_bytes: bytes) -> List[dict]:
        """
        偵測照片中的所有人臉

        Returns:
            list of dict: bbox, embedding, confidence
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("無法解碼圖片")
            return []

        # face_recognition 使用 RGB
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 偵測人臉位置
        face_locations = fr.face_locations(rgb_img, model="hog")
        # 提取 128 維特徵向量
        face_encodings = fr.face_encodings(rgb_img, face_locations)

        results = []
        for loc, encoding in zip(face_locations, face_encodings):
            top, right, bottom, left = loc
            results.append({
                "bbox": [float(left), float(top), float(right), float(bottom)],
                "embedding": encoding,  # 128 維 numpy array
                "confidence": 1.0,
            })

        logger.info(f"偵測到 {len(results)} 張人臉")
        return results

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        e1 = embedding1 / np.linalg.norm(embedding1)
        e2 = embedding2 / np.linalg.norm(embedding2)
        return float(np.dot(e1, e2))


face_service = FaceRecognitionService()
