from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ReminderResponse, DailyRemindersResponse
from app.services import contact_service

router = APIRouter(prefix="/api/v1", tags=["reminders"])


@router.get("/reminders/today", response_model=DailyRemindersResponse)
async def get_today_reminders(db: AsyncSession = Depends(get_db)):
    """
    取得今日所有提醒（供 n8n 每日排程呼叫）

    包含：
    - 近期生日提醒
    - 超過聯繫頻率的聯絡人
    """
    # 近期生日（7 天內）
    birthday_contacts = await contact_service.get_upcoming_birthdays(db, days=7)
    birthdays = []
    today = date.today()
    for contact in birthday_contacts:
        this_year_bday = contact.birthday.replace(year=today.year)
        if this_year_bday < today:
            this_year_bday = contact.birthday.replace(year=today.year + 1)
        days_until = (this_year_bday - today).days

        if days_until == 0:
            msg = f"🎂 今天是 {contact.name} 的生日！"
        else:
            msg = f"🎂 {contact.name} 的生日在 {days_until} 天後（{this_year_bday.strftime('%m/%d')}）"

        birthdays.append(ReminderResponse(
            contact_id=contact.id,
            contact_name=contact.name,
            reminder_type="birthday",
            message=msg,
        ))

    # 超過聯繫頻率
    overdue_data = await contact_service.get_overdue_contacts(db)
    overdue = []
    for item in overdue_data:
        contact = item["contact"]
        days = item["days_overdue"]
        if days is None:
            msg = f"⏰ {contact.name}（從未聯絡過，目標：每 {contact.contact_frequency_days} 天）"
        else:
            msg = f"⏰ {contact.name} 已超過聯繫頻率 {days} 天（目標：每 {contact.contact_frequency_days} 天）"

        overdue.append(ReminderResponse(
            contact_id=contact.id,
            contact_name=contact.name,
            reminder_type="contact_freq",
            message=msg,
            days_overdue=days,
        ))

    total = len(birthdays) + len(overdue)
    return DailyRemindersResponse(
        birthdays=birthdays,
        overdue_contacts=overdue,
        total=total,
    )


@router.get("/contacts/upcoming-birthdays")
async def get_upcoming_birthdays(
    days: int = Query(7, ge=1, le=90, description="查詢未來幾天內的生日"),
    db: AsyncSession = Depends(get_db),
):
    """查詢近期生日"""
    contacts = await contact_service.get_upcoming_birthdays(db, days=days)
    today = date.today()
    results = []
    for contact in contacts:
        this_year_bday = contact.birthday.replace(year=today.year)
        if this_year_bday < today:
            this_year_bday = contact.birthday.replace(year=today.year + 1)
        days_until = (this_year_bday - today).days
        results.append({
            "contact_id": str(contact.id),
            "name": contact.name,
            "birthday": contact.birthday.isoformat(),
            "days_until": days_until,
        })
    return {"upcoming_birthdays": results, "total": len(results)}


@router.get("/reminders/overdue")
async def get_overdue_contacts(db: AsyncSession = Depends(get_db)):
    """查詢超過聯繫頻率的聯絡人"""
    overdue_data = await contact_service.get_overdue_contacts(db)
    results = []
    for item in overdue_data:
        contact = item["contact"]
        results.append({
            "contact_id": str(contact.id),
            "name": contact.name,
            "contact_frequency_days": contact.contact_frequency_days,
            "last_seen_at": contact.last_seen_at.isoformat() if contact.last_seen_at else None,
            "last_greeted_at": contact.last_greeted_at.isoformat() if contact.last_greeted_at else None,
            "days_overdue": item["days_overdue"],
        })
    return {"overdue_contacts": results, "total": len(results)}
