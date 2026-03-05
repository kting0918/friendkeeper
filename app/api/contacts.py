import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    ContactCreate, ContactUpdate, ContactResponse, ContactListResponse,
    EncounterResponse, EncounterListResponse, StatsResponse,
)
from app.services import contact_service

router = APIRouter(prefix="/api/v1", tags=["contacts"])


@router.post("/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(data: ContactCreate, db: AsyncSession = Depends(get_db)):
    """新增聯絡人"""
    contact = await contact_service.create_contact(db, **data.model_dump(exclude_none=True))
    face_count = await contact_service.get_contact_face_count(db, contact.id)
    resp = ContactResponse.model_validate(contact)
    resp.face_count = face_count
    return resp


@router.get("/contacts", response_model=ContactListResponse)
async def list_contacts(
    tag: Optional[str] = Query(None, description="依關係標籤篩選"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """查詢所有聯絡人"""
    contacts, total = await contact_service.get_all_contacts(db, tag=tag, limit=limit, offset=offset)
    items = []
    for c in contacts:
        face_count = await contact_service.get_contact_face_count(db, c.id)
        resp = ContactResponse.model_validate(c)
        resp.face_count = face_count
        items.append(resp)
    return ContactListResponse(contacts=items, total=total)


@router.get("/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """查詢單一聯絡人"""
    contact = await contact_service.get_contact_by_id(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="聯絡人不存在")
    face_count = await contact_service.get_contact_face_count(db, contact.id)
    resp = ContactResponse.model_validate(contact)
    resp.face_count = face_count
    return resp


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新聯絡人資料"""
    contact = await contact_service.update_contact(
        db, contact_id, **data.model_dump(exclude_none=True)
    )
    if not contact:
        raise HTTPException(status_code=404, detail="聯絡人不存在")
    face_count = await contact_service.get_contact_face_count(db, contact.id)
    resp = ContactResponse.model_validate(contact)
    resp.face_count = face_count
    return resp


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """刪除聯絡人"""
    success = await contact_service.delete_contact(db, contact_id)
    if not success:
        raise HTTPException(status_code=404, detail="聯絡人不存在")


@router.get("/contacts/{contact_id}/encounters", response_model=EncounterListResponse)
async def list_contact_encounters(
    contact_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查詢某位聯絡人的互動記錄"""
    contact = await contact_service.get_contact_by_id(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="聯絡人不存在")

    encounters = await contact_service.get_encounters_by_contact(db, contact_id, limit=limit)
    items = []
    for e in encounters:
        resp = EncounterResponse.model_validate(e)
        resp.contact_name = contact.name
        items.append(resp)
    return EncounterListResponse(encounters=items, total=len(items))


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """取得整體統計資料"""
    stats = await contact_service.get_stats(db)
    return StatsResponse(**stats)
