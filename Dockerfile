FROM python:3.11-slim

# 安裝系統依賴（OpenCV 和 InsightFace 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安裝 Python 依賴（利用 Docker 快取層）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 預先下載 InsightFace 模型（避免每次啟動都下載）
RUN python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=0, det_size=(640, 640)); print('Model downloaded')"

# 複製程式碼
COPY . .

# 建立上傳目錄
RUN mkdir -p /app/uploads

# 暴露端口
EXPOSE 8000

# 啟動指令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
