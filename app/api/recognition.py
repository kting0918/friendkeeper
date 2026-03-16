import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.schemas import RecognitionResult, FaceMatch, FaceDetection
from app.services.face_recognition import face_service
from app.services.scene_description import describe_scene
from app.services.photo_metadata import extract_photo_time, extract_photo_location
from app.services import contact_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recognition"])


@router.post("/recognize", response_model=RecognitionResult)
async def recognize_faces(
    photo: UploadFile = File(..., description="要辨識的照片"),
    db: AsyncSession = Depends(get_db),
):
    """
    辨識照片中的人臉

    1. 偵測所有人臉並提取特徵向量
    2. 與資料庫中的已知人臉比對
    3. 使用 GPT-4o 描述場景
    4. 提取照片 EXIF 元資料
    """
    # 讀取照片
    image_bytes = await photo.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="照片檔案為空")

    # 1. 偵測人臉
    detected_faces = face_service.detect_faces(image_bytes)

    if not detected_faces:
        return RecognitionResult(
            recognized=[],
            unknown=[],
            total_faces=0,
            scene_description=None,
        )

    # 2. 比對每張人臉
    recognized = []
    unknown = []

    for face_data in detected_faces:
        embedding = face_data["embedding"].tolist()

        # 在資料庫中搜尋相似人臉
        matches = await contact_service.find_similar_faces(
            db, embedding, threshold=settings.face_similarity_threshold
        )

        if matches:
            best_match = matches[0]
            recognized.append(FaceMatch(
                contact_id=best_match["contact_id"],
                contact_name=best_match["contact_name"],
                similarity=best_match["similarity"],
                bbox=face_data["bbox"],
            ))
        else:
            unknown.append(FaceDetection(
                bbox=face_data["bbox"],
                confidence=face_data["confidence"],
            ))

    # 3. AI 場景描述（非同步，與辨識平行處理）
    recognized_names = [r.contact_name for r in recognized]
    scene_desc = await describe_scene(image_bytes, recognized_names)

    # 4. 提取照片元資料
    photo_time = extract_photo_time(image_bytes)
    photo_loc = extract_photo_location(image_bytes)
    photo_location = None
    if photo_loc:
        photo_location = {"lat": photo_loc[0], "lng": photo_loc[1]}

    return RecognitionResult(
        recognized=recognized,
        unknown=unknown,
        scene_description=scene_desc,
        photo_time=photo_time,
        photo_location=photo_location,
        total_faces=len(detected_faces),
    )


@router.post("/faces/register", status_code=201)
async def register_face(
    photo: UploadFile = File(..., description="包含人臉的照片"),
    contact_id: str = Form(..., description="聯絡人 ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    為聯絡人註冊新的人臉特徵

    上傳一張照片，系統會偵測人臉並儲存特徵向量。
    建議為每位聯絡人註冊 3-5 張不同角度的照片以提升辨識準確度。
    """
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="無效的 contact_id")

    # 確認聯絡人存在
    contact = await contact_service.get_contact_by_id(db, cid)
    if not contact:
        raise HTTPException(status_code=404, detail="聯絡人不存在")

    # 讀取照片
    image_bytes = await photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="照片檔案為空")

    # 偵測人臉
    detected_faces = face_service.detect_faces(image_bytes)

    if not detected_faces:
        raise HTTPException(status_code=400, detail="照片中未偵測到人臉")

    if len(detected_faces) > 1:
        # 多人照片：取最大的人臉（假設是主要對象）
        detected_faces.sort(
            key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]),
            reverse=True,
        )

    # 儲存第一張（最大的）人臉特徵
    face_data = detected_faces[0]
    embedding = face_data["embedding"].tolist()

    # 儲存照片（可選）
    photo_url = None
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{cid}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = upload_dir / filename
    filepath.write_bytes(image_bytes)
    photo_url = str(filepath)

    # 儲存特徵向量
    face_embedding = await contact_service.save_face_embedding(
        db, contact_id=cid, embedding=embedding, source_photo_url=photo_url
    )

    return {
        "message": f"已為 {contact.name} 註冊人臉特徵",
        "face_id": str(face_embedding.id),
        "contact_id": str(cid),
        "contact_name": contact.name,
    }


@router.post("/process-photo")
async def process_photo(
    photo: UploadFile = File(..., description="要處理的照片"),
    db: AsyncSession = Depends(get_db),
):
    """
    完整的照片處理流程（給 n8n 呼叫的一站式端點）

    1. 辨識人臉
    2. AI 場景描述
    3. 自動建立互動記錄
    4. 回傳處理結果（供 Telegram Bot 回覆）
    """
    image_bytes = await photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="照片檔案為空")

    # 偵測人臉
    detected_faces = face_service.detect_faces(image_bytes)

    # 提取元資料
    photo_time = extract_photo_time(image_bytes) or datetime.utcnow()
    photo_loc = extract_photo_location(image_bytes)

    if not detected_faces:
        return {
            "status": "no_faces",
            "message": "照片中未偵測到人臉",
            "total_faces": 0,
        }

    # 比對人臉
    recognized = []
    unknown_count = 0
    auto_learned = []  # 自動學習的 embedding

    # 自動學習門檻：辨識信心值 > 0.85 才追加，避免誤判汙染資料
    AUTO_LEARN_THRESHOLD = 0.85
    MAX_EMBEDDINGS_PER_CONTACT = 20

    for face_data in detected_faces:
        embedding = face_data["embedding"].tolist()
        matches = await contact_service.find_similar_faces(
            db, embedding, threshold=settings.face_similarity_threshold
        )
        if matches:
            best = matches[0]
            recognized.append(best)

            # 高信心值時自動追加 embedding（越用越準）
            if best["similarity"] >= AUTO_LEARN_THRESHOLD:
                face_count = await contact_service.get_contact_face_count(
                    db, best["contact_id"]
                )
                if face_count < MAX_EMBEDDINGS_PER_CONTACT:
                    await contact_service.save_face_embedding(
                        db,
                        contact_id=best["contact_id"],
                        embedding=embedding,
                        source_photo_url=None,
                    )
                    auto_learned.append(best["contact_name"])
                    logger.info(
                        f"自動學習：{best['contact_name']} "
                        f"(similarity={best['similarity']:.3f}, "
                        f"total={face_count + 1})"
                    )
        else:
            unknown_count += 1

    # AI 場景描述
    recognized_names = [r["contact_name"] for r in recognized]
    scene_desc = await describe_scene(image_bytes, recognized_names)

    # 儲存照片
    photo_url = None
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"encounter_{uuid.uuid4().hex[:8]}.jpg"
    filepath = upload_dir / filename
    filepath.write_bytes(image_bytes)
    photo_url = str(filepath)

    # 為每位辨識到的人建立互動記錄
    encounter_results = []
    for match in recognized:
        encounter = await contact_service.create_encounter(
            db,
            contact_id=match["contact_id"],
            encountered_at=photo_time,
            location_lat=photo_loc[0] if photo_loc else None,
            location_lng=photo_loc[1] if photo_loc else None,
            photo_url=photo_url,
            scene_description=scene_desc,
            source="photo",
        )
        encounter_results.append({
            "contact_name": match["contact_name"],
            "similarity": round(match["similarity"], 3),
            "encounter_id": str(encounter.id),
        })

    # 組裝回覆訊息
    if recognized:
        names = "、".join([r["contact_name"] for r in recognized])
        message = f"📸 辨識到：{names}\n"
        message += f"⏰ 時間：{photo_time.strftime('%Y-%m-%d %H:%M')}\n"
        if scene_desc:
            message += f"🏷️ 場景：{scene_desc}\n"
        message += f"✅ 已記錄 {len(recognized)} 筆見面紀錄"
        if auto_learned:
            message += f"\n🧠 已自動學習 {', '.join(auto_learned)} 的新面部特徵"
    else:
        message = "🤔 未能辨識出照片中的任何人"

    if unknown_count > 0:
        message += f"\n❓ 另有 {unknown_count} 張未知人臉"

    return {
        "status": "success" if recognized else "unknown",
        "message": message,
        "recognized": encounter_results,
        "unknown_count": unknown_count,
        "scene_description": scene_desc,
        "photo_time": photo_time.isoformat() if photo_time else None,
        "total_faces": len(detected_faces),
    }
