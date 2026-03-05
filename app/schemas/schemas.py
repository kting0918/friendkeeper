import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ─── Contact Schemas ───

class ContactCreate(BaseModel):
    name: str = Field(..., max_length=100, description="聯絡人姓名")
    nickname: Optional[str] = Field(None, max_length=100, description="暱稱")
    birthday: Optional[date] = Field(None, description="生日")
    relationship_tag: Optional[str] = Field(None, max_length=50, description="關係標籤")
    contact_frequency_days: Optional[int] = Field(None, ge=1, description="目標聯繫頻率（天）")
    notes: Optional[str] = Field(None, description="備註")


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    nickname: Optional[str] = Field(None, max_length=100)
    birthday: Optional[date] = None
    relationship_tag: Optional[str] = Field(None, max_length=50)
    contact_frequency_days: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None
    last_greeted_at: Optional[datetime] = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    name: str
    nickname: Optional[str]
    birthday: Optional[date]
    relationship_tag: Optional[str]
    contact_frequency_days: Optional[int]
    last_seen_at: Optional[datetime]
    last_greeted_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    face_count: int = 0  # 已註冊的人臉數量

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    contacts: List[ContactResponse]
    total: int


# ─── Encounter Schemas ───

class EncounterCreate(BaseModel):
    contact_id: uuid.UUID
    encountered_at: datetime
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_name: Optional[str] = None
    photo_url: Optional[str] = None
    note: Optional[str] = None
    scene_description: Optional[str] = None
    source: str = "photo"


class EncounterResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str = ""
    encountered_at: datetime
    location_lat: Optional[float]
    location_lng: Optional[float]
    location_name: Optional[str]
    photo_url: Optional[str]
    note: Optional[str]
    scene_description: Optional[str]
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EncounterListResponse(BaseModel):
    encounters: List[EncounterResponse]
    total: int


# ─── Face Recognition Schemas ───

class FaceDetection(BaseModel):
    """單一偵測到的人臉"""
    bbox: List[float] = Field(description="人臉邊界框 [x1, y1, x2, y2]")
    confidence: float = Field(description="偵測信心度")


class FaceMatch(BaseModel):
    """人臉比對結果"""
    contact_id: uuid.UUID
    contact_name: str
    similarity: float
    bbox: List[float]


class RecognitionResult(BaseModel):
    """整張照片的辨識結果"""
    recognized: List[FaceMatch] = Field(default_factory=list, description="成功辨識的人臉")
    unknown: List[FaceDetection] = Field(default_factory=list, description="無法辨識的人臉")
    scene_description: Optional[str] = Field(None, description="AI 生成的場景描述")
    photo_time: Optional[datetime] = Field(None, description="照片拍攝時間")
    photo_location: Optional[dict] = Field(None, description="照片拍攝地點")
    total_faces: int = 0


# ─── Reminder Schemas ───

class ReminderResponse(BaseModel):
    contact_id: uuid.UUID
    contact_name: str
    reminder_type: str
    message: str
    days_overdue: Optional[int] = None

    model_config = {"from_attributes": True}


class DailyRemindersResponse(BaseModel):
    birthdays: List[ReminderResponse] = Field(default_factory=list)
    overdue_contacts: List[ReminderResponse] = Field(default_factory=list)
    total: int = 0


# ─── Stats Schemas ───

class StatsResponse(BaseModel):
    total_contacts: int
    total_encounters: int
    contacts_seen_this_week: int
    contacts_seen_this_month: int
    overdue_contacts: int  # 超過聯繫頻率的人數
    upcoming_birthdays: int  # 7 天內的生日
