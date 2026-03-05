import uuid
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List

from sqlalchemy import select, func, and_, or_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Contact, FaceEmbedding, Encounter, Reminder

logger = logging.getLogger(__name__)


# ─── Contact CRUD ───

async def create_contact(db: AsyncSession, name: str, **kwargs) -> Contact:
    """建立新聯絡人"""
    contact = Contact(name=name, **kwargs)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    logger.info(f"建立聯絡人：{name} (id={contact.id})")
    return contact


async def get_contact_by_id(db: AsyncSession, contact_id: uuid.UUID) -> Optional[Contact]:
    """依 ID 查詢聯絡人"""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id)
    )
    return result.scalar_one_or_none()


async def get_contact_by_name(db: AsyncSession, name: str) -> Optional[Contact]:
    """依名稱查詢聯絡人（模糊比對）"""
    result = await db.execute(
        select(Contact).where(
            or_(Contact.name == name, Contact.nickname == name)
        )
    )
    return result.scalar_one_or_none()


async def get_all_contacts(
    db: AsyncSession,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[List[Contact], int]:
    """查詢所有聯絡人"""
    query = select(Contact)
    count_query = select(func.count(Contact.id))

    if tag:
        query = query.where(Contact.relationship_tag == tag)
        count_query = count_query.where(Contact.relationship_tag == tag)

    query = query.order_by(Contact.name).limit(limit).offset(offset)

    result = await db.execute(query)
    contacts = list(result.scalars().all())

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return contacts, total


async def update_contact(db: AsyncSession, contact_id: uuid.UUID, **kwargs) -> Optional[Contact]:
    """更新聯絡人資料"""
    contact = await get_contact_by_id(db, contact_id)
    if not contact:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(contact, key):
            setattr(contact, key, value)

    await db.flush()
    await db.refresh(contact)
    return contact


async def delete_contact(db: AsyncSession, contact_id: uuid.UUID) -> bool:
    """刪除聯絡人"""
    contact = await get_contact_by_id(db, contact_id)
    if not contact:
        return False
    await db.delete(contact)
    await db.flush()
    return True


async def get_contact_face_count(db: AsyncSession, contact_id: uuid.UUID) -> int:
    """取得聯絡人的人臉數量"""
    result = await db.execute(
        select(func.count(FaceEmbedding.id)).where(FaceEmbedding.contact_id == contact_id)
    )
    return result.scalar() or 0


# ─── Face Embedding ───

async def save_face_embedding(
    db: AsyncSession,
    contact_id: uuid.UUID,
    embedding: list,
    source_photo_url: Optional[str] = None,
) -> FaceEmbedding:
    """儲存人臉特徵向量"""
    face = FaceEmbedding(
        contact_id=contact_id,
        embedding=embedding,
        source_photo_url=source_photo_url,
    )
    db.add(face)
    await db.flush()
    logger.info(f"儲存人臉特徵向量 contact_id={contact_id}")
    return face


async def get_all_face_embeddings(db: AsyncSession) -> List[FaceEmbedding]:
    """取得所有人臉特徵向量（用於比對）"""
    result = await db.execute(
        select(FaceEmbedding).options(selectinload(FaceEmbedding.contact))
    )
    return list(result.scalars().all())


async def find_similar_faces(
    db: AsyncSession,
    embedding: list,
    threshold: float = 0.6,
    limit: int = 1,
) -> List[dict]:
    """
    使用 pgvector 搜尋相似的人臉

    Args:
        embedding: 查詢的特徵向量
        threshold: 相似度閾值
        limit: 回傳結果數量

    Returns:
        list of dict，每個包含 contact_id, contact_name, similarity
    """
    from pgvector.sqlalchemy import Vector
    from sqlalchemy import text

    # 使用 pgvector 的餘弦距離搜尋
    # 注意：pgvector 的 <=> 是餘弦距離（0 = 完全相同，2 = 完全不同）
    # 相似度 = 1 - 距離
    query = text("""
        SELECT
            fe.contact_id,
            c.name as contact_name,
            1 - (fe.embedding <=> :embedding::vector) as similarity
        FROM face_embeddings fe
        JOIN contacts c ON c.id = fe.contact_id
        WHERE 1 - (fe.embedding <=> :embedding::vector) >= :threshold
        ORDER BY fe.embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(
        query,
        {
            "embedding": str(embedding),
            "threshold": threshold,
            "limit": limit,
        },
    )

    matches = []
    for row in result:
        matches.append({
            "contact_id": row.contact_id,
            "contact_name": row.contact_name,
            "similarity": float(row.similarity),
        })

    return matches


# ─── Encounters ───

async def create_encounter(db: AsyncSession, **kwargs) -> Encounter:
    """建立互動記錄"""
    encounter = Encounter(**kwargs)
    db.add(encounter)
    await db.flush()

    # 同步更新聯絡人的 last_seen_at
    contact = await get_contact_by_id(db, kwargs["contact_id"])
    if contact:
        if kwargs.get("source") == "greeting":
            contact.last_greeted_at = kwargs["encountered_at"]
        else:
            contact.last_seen_at = kwargs["encountered_at"]
        await db.flush()

    return encounter


async def get_encounters_by_contact(
    db: AsyncSession,
    contact_id: uuid.UUID,
    limit: int = 20,
) -> List[Encounter]:
    """查詢某位聯絡人的互動記錄"""
    result = await db.execute(
        select(Encounter)
        .where(Encounter.contact_id == contact_id)
        .order_by(Encounter.encountered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ─── Reminders ───

async def get_upcoming_birthdays(db: AsyncSession, days: int = 7) -> List[Contact]:
    """查詢近期生日的聯絡人"""
    today = date.today()
    contacts_result = await db.execute(
        select(Contact).where(Contact.birthday.isnot(None))
    )
    contacts = list(contacts_result.scalars().all())

    upcoming = []
    for contact in contacts:
        # 計算今年的生日
        this_year_birthday = contact.birthday.replace(year=today.year)
        if this_year_birthday < today:
            this_year_birthday = contact.birthday.replace(year=today.year + 1)

        delta = (this_year_birthday - today).days
        if 0 <= delta <= days:
            upcoming.append(contact)

    return upcoming


async def get_overdue_contacts(db: AsyncSession) -> List[dict]:
    """查詢超過聯繫頻率的聯絡人"""
    now = datetime.utcnow()
    result = await db.execute(
        select(Contact).where(
            and_(
                Contact.contact_frequency_days.isnot(None),
                Contact.contact_frequency_days > 0,
            )
        )
    )
    contacts = list(result.scalars().all())

    overdue = []
    for contact in contacts:
        # 取 last_seen_at 和 last_greeted_at 中較新的
        last_contact = max(
            filter(None, [contact.last_seen_at, contact.last_greeted_at]),
            default=None,
        )
        if last_contact is None:
            # 從未聯絡過
            overdue.append({
                "contact": contact,
                "days_overdue": None,  # 從未聯絡
            })
        else:
            # 確保 last_contact 是 naive datetime 以便比較
            if last_contact.tzinfo:
                last_contact = last_contact.replace(tzinfo=None)
            days_since = (now - last_contact).days
            if days_since > contact.contact_frequency_days:
                overdue.append({
                    "contact": contact,
                    "days_overdue": days_since - contact.contact_frequency_days,
                })

    return overdue


# ─── Stats ───

async def get_stats(db: AsyncSession) -> dict:
    """取得整體統計資料"""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    total_encounters = (await db.execute(select(func.count(Encounter.id)))).scalar() or 0

    seen_this_week = (await db.execute(
        select(func.count(func.distinct(Encounter.contact_id)))
        .where(Encounter.encountered_at >= week_ago)
    )).scalar() or 0

    seen_this_month = (await db.execute(
        select(func.count(func.distinct(Encounter.contact_id)))
        .where(Encounter.encountered_at >= month_ago)
    )).scalar() or 0

    overdue = await get_overdue_contacts(db)
    upcoming = await get_upcoming_birthdays(db)

    return {
        "total_contacts": total_contacts,
        "total_encounters": total_encounters,
        "contacts_seen_this_week": seen_this_week,
        "contacts_seen_this_month": seen_this_month,
        "overdue_contacts": len(overdue),
        "upcoming_birthdays": len(upcoming),
    }
