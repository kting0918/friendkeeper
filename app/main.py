import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api import contacts, recognition, reminders, bot_commands

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    port = os.environ.get("PORT", "8000")
    logger.info(f"🚀 FriendKeeper 啟動中... (PORT={port})")
    # 初始化資料庫
    await init_db()
    logger.info("✅ 資料庫初始化完成")
    # 預載人臉辨識模型
    try:
        from app.services.face_service import face_service
        logger.info("✅ 人臉辨識服務就緒")
    except Exception as e:
        logger.warning(f"⚠️ 人臉辨識服務載入失敗（可稍後重試）：{e}")
    yield
    logger.info("👋 FriendKeeper 關閉")


app = FastAPI(
    title="FriendKeeper API",
    description="個人社交關係管理系統 - 透過照片人臉辨識自動管理人際互動",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(contacts.router)
app.include_router(recognition.router)
app.include_router(reminders.router)
app.include_router(bot_commands.router)


@app.get("/", tags=["health"])
async def root():
    return {"service": "FriendKeeper", "status": "running", "version": "1.0.0"}


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy"}
