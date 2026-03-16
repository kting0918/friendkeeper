import uuid
import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import contact_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bot", tags=["telegram-bot"])

# 簡易的聊天會話狀態（記錄哪個 chat_id 正在等待註冊照片）
# key: chat_id, value: {"contact_name": str, "contact_id": str, "created_at": datetime}
_registration_sessions: dict[int, dict] = {}


class BotCommandRequest(BaseModel):
    """Telegram Bot 指令請求"""
    command: str  # 指令名稱（不含 /）
    args: str = ""  # 參數文字
    chat_id: int = 0


class BotCommandResponse(BaseModel):
    """Telegram Bot 指令回應"""
    message: str
    parse_mode: str = "HTML"  # Telegram 支援 HTML 格式


@router.post("/command", response_model=BotCommandResponse)
async def handle_bot_command(
    request: BotCommandRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    處理 Telegram Bot 指令（由 n8n 轉發）

    n8n 收到 Telegram 訊息後，解析指令名稱和參數，
    透過 HTTP 呼叫此端點，再將回應轉發回 Telegram。
    """
    command = request.command.lower().strip()
    args = request.args.strip()

    try:
        if command == "info":
            return await cmd_info(db, args)
        elif command == "birthday":
            return await cmd_birthday(db, args)
        elif command == "note":
            return await cmd_note(db, args)
        elif command == "greet":
            return await cmd_greet(db, args)
        elif command == "freq":
            return await cmd_freq(db, args)
        elif command == "remind":
            return await cmd_remind(db)
        elif command == "upcoming":
            return await cmd_upcoming(db)
        elif command == "list":
            return await cmd_list(db, args)
        elif command == "tag":
            return await cmd_tag(db, args)
        elif command == "history":
            return await cmd_history(db, args)
        elif command == "stats":
            return await cmd_stats(db)
        elif command == "new":
            return await cmd_new(db, args, request.chat_id)
        elif command == "register":
            return await cmd_register(db, args, request.chat_id)
        elif command == "cancel":
            return cmd_cancel(request.chat_id)
        elif command == "help":
            return cmd_help()
        else:
            return BotCommandResponse(message=f"❓ 未知指令：/{command}\n輸入 /help 查看可用指令")
    except Exception as e:
        logger.error(f"指令處理錯誤：{e}")
        return BotCommandResponse(message=f"❌ 處理錯誤：{str(e)}")


async def cmd_info(db: AsyncSession, args: str) -> BotCommandResponse:
    """查看聯絡人資訊"""
    if not args:
        return BotCommandResponse(message="❌ 請提供姓名\n用法：/info 姓名")

    contact = await contact_service.get_contact_by_name(db, args)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{args}")

    face_count = await contact_service.get_contact_face_count(db, contact.id)
    encounters = await contact_service.get_encounters_by_contact(db, contact.id, limit=3)

    msg = f"<b>👤 {contact.name}</b>\n"
    if contact.nickname:
        msg += f"暱稱：{contact.nickname}\n"
    if contact.relationship_tag:
        msg += f"關係：{contact.relationship_tag}\n"
    if contact.birthday:
        msg += f"生日：{contact.birthday.strftime('%Y-%m-%d')}\n"
    msg += f"人臉資料：{face_count} 筆\n"

    if contact.last_seen_at:
        msg += f"上次見面：{contact.last_seen_at.strftime('%Y-%m-%d %H:%M')}\n"
    else:
        msg += "上次見面：尚無記錄\n"

    if contact.last_greeted_at:
        msg += f"上次問候：{contact.last_greeted_at.strftime('%Y-%m-%d %H:%M')}\n"

    if contact.contact_frequency_days:
        msg += f"聯繫頻率：每 {contact.contact_frequency_days} 天\n"

    if contact.notes:
        msg += f"\n📝 備註：{contact.notes}\n"

    if encounters:
        msg += "\n<b>最近互動：</b>\n"
        for e in encounters:
            time_str = e.encountered_at.strftime("%m/%d")
            source_emoji = {"photo": "📸", "manual": "✏️", "greeting": "👋"}.get(e.source, "📌")
            line = f"  {source_emoji} {time_str}"
            if e.scene_description:
                line += f" - {e.scene_description}"
            elif e.note:
                line += f" - {e.note}"
            msg += line + "\n"

    return BotCommandResponse(message=msg)


async def cmd_new(db: AsyncSession, args: str, chat_id: int = 0) -> BotCommandResponse:
    """新增聯絡人並自動進入人臉註冊模式"""
    if not args:
        return BotCommandResponse(message="❌ 請提供姓名\n用法：/new 姓名")

    existing = await contact_service.get_contact_by_name(db, args)
    if existing:
        return BotCommandResponse(message=f"⚠️ {args} 已存在，請使用其他名稱")

    contact = await contact_service.create_contact(db, name=args)

    # 自動建立註冊會話，讓使用者可以直接傳照片註冊人臉
    if chat_id:
        _registration_sessions[chat_id] = {
            "contact_name": contact.name,
            "contact_id": str(contact.id),
            "created_at": datetime.utcnow(),
        }

    return BotCommandResponse(
        message=f"✅ 已建立聯絡人：<b>{contact.name}</b>\n\n"
                f"📸 已進入<b>人臉註冊模式</b>\n"
                f"請傳送一張此人的<b>清晰正面照</b>來註冊人臉。\n"
                f"建議註冊 3-5 張不同角度的照片以提升辨識準確度。\n\n"
                f"輸入 /cancel 取消註冊"
    )


async def cmd_birthday(db: AsyncSession, args: str) -> BotCommandResponse:
    """設定生日"""
    parts = args.rsplit(" ", 1)
    if len(parts) != 2:
        return BotCommandResponse(message="❌ 用法：/birthday 姓名 YYYY-MM-DD")

    name, date_str = parts
    contact = await contact_service.get_contact_by_name(db, name)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{name}")

    try:
        birthday = date.fromisoformat(date_str)
    except ValueError:
        return BotCommandResponse(message="❌ 日期格式錯誤，請使用 YYYY-MM-DD")

    await contact_service.update_contact(db, contact.id, birthday=birthday)
    return BotCommandResponse(message=f"✅ 已設定 {name} 的生日為 {date_str}")


async def cmd_note(db: AsyncSession, args: str) -> BotCommandResponse:
    """新增備註"""
    parts = args.split(" ", 1)
    if len(parts) != 2:
        return BotCommandResponse(message="❌ 用法：/note 姓名 備註內容")

    name, note = parts
    contact = await contact_service.get_contact_by_name(db, name)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{name}")

    # 附加備註（不覆蓋舊的）
    existing_notes = contact.notes or ""
    timestamp = datetime.now().strftime("%m/%d")
    new_notes = f"{existing_notes}\n[{timestamp}] {note}".strip()
    await contact_service.update_contact(db, contact.id, notes=new_notes)
    return BotCommandResponse(message=f"✅ 已為 {name} 新增備註：{note}")


async def cmd_greet(db: AsyncSession, args: str) -> BotCommandResponse:
    """記錄問候"""
    if not args:
        return BotCommandResponse(message="❌ 請提供姓名\n用法：/greet 姓名")

    contact = await contact_service.get_contact_by_name(db, args)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{args}")

    now = datetime.utcnow()
    await contact_service.create_encounter(
        db,
        contact_id=contact.id,
        encountered_at=now,
        source="greeting",
    )
    return BotCommandResponse(message=f"👋 已記錄對 {contact.name} 的問候")


async def cmd_freq(db: AsyncSession, args: str) -> BotCommandResponse:
    """設定聯繫頻率"""
    parts = args.rsplit(" ", 1)
    if len(parts) != 2:
        return BotCommandResponse(message="❌ 用法：/freq 姓名 天數")

    name, days_str = parts
    contact = await contact_service.get_contact_by_name(db, name)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{name}")

    try:
        days = int(days_str)
        if days < 1:
            raise ValueError
    except ValueError:
        return BotCommandResponse(message="❌ 天數必須為正整數")

    await contact_service.update_contact(db, contact.id, contact_frequency_days=days)
    return BotCommandResponse(message=f"✅ 已設定 {name} 的聯繫頻率為每 {days} 天")


async def cmd_remind(db: AsyncSession) -> BotCommandResponse:
    """查看需要聯繫的人"""
    overdue = await contact_service.get_overdue_contacts(db)
    if not overdue:
        return BotCommandResponse(message="✅ 目前沒有需要聯繫的人，做得好！")

    msg = "<b>⏰ 需要聯繫的人：</b>\n\n"
    for item in overdue:
        contact = item["contact"]
        days = item["days_overdue"]
        if days is None:
            msg += f"• {contact.name}（從未聯絡過）\n"
        else:
            msg += f"• {contact.name}（超過 {days} 天）\n"

    return BotCommandResponse(message=msg)


async def cmd_upcoming(db: AsyncSession) -> BotCommandResponse:
    """查看近期生日"""
    contacts = await contact_service.get_upcoming_birthdays(db, days=30)
    if not contacts:
        return BotCommandResponse(message="📅 近 30 天內沒有生日")

    today = date.today()
    msg = "<b>🎂 近期生日：</b>\n\n"
    for contact in contacts:
        this_year_bday = contact.birthday.replace(year=today.year)
        if this_year_bday < today:
            this_year_bday = contact.birthday.replace(year=today.year + 1)
        days_until = (this_year_bday - today).days

        if days_until == 0:
            msg += f"🎉 <b>{contact.name}</b> - 今天！\n"
        else:
            msg += f"• {contact.name} - {this_year_bday.strftime('%m/%d')}（{days_until} 天後）\n"

    return BotCommandResponse(message=msg)


async def cmd_list(db: AsyncSession, args: str) -> BotCommandResponse:
    """列出聯絡人"""
    tag = args if args else None
    contacts, total = await contact_service.get_all_contacts(db, tag=tag)

    if not contacts:
        if tag:
            return BotCommandResponse(message=f"📋 沒有標籤為「{tag}」的聯絡人")
        return BotCommandResponse(message="📋 目前沒有任何聯絡人\n使用 /new 姓名 來新增")

    title = f"標籤：{tag}" if tag else "所有聯絡人"
    msg = f"<b>📋 {title}（共 {total} 人）：</b>\n\n"
    for c in contacts:
        tag_str = f" [{c.relationship_tag}]" if c.relationship_tag else ""
        last_seen = ""
        if c.last_seen_at:
            last_seen = f" - 上次見面 {c.last_seen_at.strftime('%m/%d')}"
        msg += f"• {c.name}{tag_str}{last_seen}\n"

    return BotCommandResponse(message=msg)


async def cmd_tag(db: AsyncSession, args: str) -> BotCommandResponse:
    """設定關係標籤"""
    parts = args.split(" ", 1)
    if len(parts) != 2:
        return BotCommandResponse(message="❌ 用法：/tag 姓名 標籤")

    name, tag = parts
    contact = await contact_service.get_contact_by_name(db, name)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{name}")

    await contact_service.update_contact(db, contact.id, relationship_tag=tag)
    return BotCommandResponse(message=f"✅ 已將 {name} 標記為「{tag}」")


async def cmd_history(db: AsyncSession, args: str) -> BotCommandResponse:
    """查看互動歷史"""
    if not args:
        return BotCommandResponse(message="❌ 請提供姓名\n用法：/history 姓名")

    contact = await contact_service.get_contact_by_name(db, args)
    if not contact:
        return BotCommandResponse(message=f"❌ 找不到聯絡人：{args}")

    encounters = await contact_service.get_encounters_by_contact(db, contact.id, limit=20)
    if not encounters:
        return BotCommandResponse(message=f"📜 與 {contact.name} 暫無互動記錄")

    msg = f"<b>📜 與 {contact.name} 的互動記錄：</b>\n\n"
    for e in encounters:
        time_str = e.encountered_at.strftime("%Y-%m-%d %H:%M")
        source_emoji = {"photo": "📸", "manual": "✏️", "greeting": "👋"}.get(e.source, "📌")
        msg += f"{source_emoji} {time_str}"
        if e.location_name:
            msg += f" 📍 {e.location_name}"
        if e.scene_description:
            msg += f"\n   🏷️ {e.scene_description}"
        elif e.note:
            msg += f"\n   📝 {e.note}"
        msg += "\n\n"

    return BotCommandResponse(message=msg)


async def cmd_stats(db: AsyncSession) -> BotCommandResponse:
    """查看統計"""
    stats = await contact_service.get_stats(db)

    msg = "<b>📊 FriendKeeper 統計</b>\n\n"
    msg += f"👥 總聯絡人數：{stats['total_contacts']}\n"
    msg += f"📸 總互動記錄：{stats['total_encounters']}\n"
    msg += f"🗓️ 本週見面：{stats['contacts_seen_this_week']} 人\n"
    msg += f"📅 本月見面：{stats['contacts_seen_this_month']} 人\n"
    msg += f"⏰ 需要聯繫：{stats['overdue_contacts']} 人\n"
    msg += f"🎂 近期生日：{stats['upcoming_birthdays']} 人\n"

    return BotCommandResponse(message=msg)


async def cmd_register(db: AsyncSession, args: str, chat_id: int) -> BotCommandResponse:
    """進入人臉註冊模式"""
    if not args:
        return BotCommandResponse(message="❌ 請提供姓名\n用法：/register 姓名")

    contact = await contact_service.get_contact_by_name(db, args)
    if not contact:
        return BotCommandResponse(
            message=f"❌ 找不到聯絡人：{args}\n請先用 /new {args} 建立聯絡人"
        )

    face_count = await contact_service.get_contact_face_count(db, contact.id)

    # 設定註冊會話
    _registration_sessions[chat_id] = {
        "contact_name": contact.name,
        "contact_id": str(contact.id),
        "created_at": datetime.utcnow(),
    }

    msg = f"📸 <b>人臉註冊模式</b>\n\n"
    msg += f"正在為 <b>{contact.name}</b> 註冊人臉"
    msg += f"（目前已有 {face_count} 筆資料）\n\n"
    msg += "請傳送一張此人的<b>清晰正面照</b>。\n"
    msg += "建議註冊 3-5 張不同角度的照片以提升辨識準確度。\n\n"
    msg += "輸入 /cancel 取消註冊"

    return BotCommandResponse(message=msg)


def cmd_cancel(chat_id: int) -> BotCommandResponse:
    """取消註冊模式"""
    if chat_id in _registration_sessions:
        name = _registration_sessions.pop(chat_id)["contact_name"]
        return BotCommandResponse(message=f"✅ 已取消為 {name} 的人臉註冊")
    return BotCommandResponse(message="ℹ️ 目前沒有進行中的註冊")


@router.get("/registration-session")
async def check_registration_session(chat_id: int):
    """
    檢查指定 chat_id 是否有進行中的人臉註冊會話

    n8n 在收到照片時先呼叫此端點：
    - 如果有註冊會話 → 走人臉註冊流程
    - 如果沒有 → 走一般的人臉辨識流程
    """
    session = _registration_sessions.get(chat_id)
    if session:
        # 檢查是否過期（30 分鐘）
        elapsed = (datetime.utcnow() - session["created_at"]).total_seconds()
        if elapsed > 1800:
            _registration_sessions.pop(chat_id, None)
            return {"has_session": False}
        return {
            "has_session": True,
            "contact_name": session["contact_name"],
            "contact_id": session["contact_id"],
        }
    return {"has_session": False}


@router.post("/registration-complete")
async def complete_registration(chat_id: int):
    """
    完成一次人臉註冊後呼叫（不自動清除會話，允許連續註冊多張照片）

    n8n 在人臉註冊成功後呼叫此端點，回傳訊息給使用者
    """
    session = _registration_sessions.get(chat_id)
    if not session:
        return {"message": "ℹ️ 註冊會話已結束"}

    return {
        "message": (
            f"✅ 已為 <b>{session['contact_name']}</b> 註冊一筆人臉資料！\n\n"
            f"你可以繼續傳照片來增加更多角度，\n"
            f"或輸入 /cancel 結束註冊模式。"
        )
    }


def cmd_help() -> BotCommandResponse:
    """顯示說明"""
    msg = """<b>🤖 FriendKeeper 指令說明</b>

<b>📸 照片辨識</b>
直接傳送照片 → 自動辨識並記錄見面

<b>👤 聯絡人管理</b>
/new 姓名 → 新增聯絡人
/register 姓名 → 註冊人臉（傳照片）
/info 姓名 → 查看資訊
/list [標籤] → 列出聯絡人
/tag 姓名 標籤 → 設定關係標籤
/note 姓名 內容 → 新增備註

<b>📅 時間管理</b>
/birthday 姓名 日期 → 設定生日
/freq 姓名 天數 → 設定聯繫頻率
/greet 姓名 → 記錄問候

<b>🔔 提醒與統計</b>
/remind → 需要聯繫的人
/upcoming → 近期生日
/history 姓名 → 互動歷史
/stats → 整體統計

<b>⚙️ 其他</b>
/cancel → 取消目前操作"""

    return BotCommandResponse(message=msg)
