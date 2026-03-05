# 🚀 FriendKeeper 部署教學

## 概覽

部署 FriendKeeper 一共需要完成 5 個步驟，全部操作大約 30-60 分鐘。

```
步驟 1：申請 Telegram Bot（5 分鐘）
步驟 2：把程式碼上傳到 GitHub（5 分鐘）
步驟 3：在 Zeabur 上部署服務（15 分鐘）
步驟 4：設定環境變數（5 分鐘）
步驟 5：匯入 n8n 工作流（10 分鐘）
```

---

## 步驟 1：申請 Telegram Bot

1. 在 Telegram 搜尋 `@BotFather` 並打開對話
2. 發送 `/newbot`
3. 輸入 Bot 名稱，例如 `FriendKeeper`
4. 輸入 Bot 的 username，例如 `my_friendkeeper_bot`（必須以 `_bot` 結尾）
5. BotFather 會回覆一個 **Token**，格式像這樣：
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
6. **複製並保存這個 Token**，稍後會用到

### 取得你的 Chat ID

1. 在 Telegram 搜尋 `@userinfobot` 並打開對話
2. 發送 `/start`
3. 它會回覆你的 Chat ID（一個數字），**記下來**

---

## 步驟 2：上傳到 GitHub

1. 在 GitHub 建立一個新的 Repository
   - 名稱：`friendkeeper`
   - 設為 Private（因為包含部署設定）

2. 把整個專案資料夾推上去：
   ```bash
   cd friendkeeper
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/你的帳號/friendkeeper.git
   git push -u origin main
   ```

---

## 步驟 3：在 Zeabur 部署

### 3.1 建立專案

1. 登入 [Zeabur](https://zeabur.com)
2. 點擊 **Create Project**
3. 選擇一個區域（建議選離你最近的，例如 `Asia - Taiwan`）

### 3.2 部署 PostgreSQL

1. 在專案中點擊 **Add Service** → **Marketplace**
2. 搜尋 `PostgreSQL`，點擊部署
3. 部署完成後，點進 PostgreSQL 服務
4. 在 **Connection** 頁面，找到並複製 **Connection String**（格式是 `postgresql://...`）
5. **重要**：把連線字串中的 `postgresql://` 改為 `postgresql+asyncpg://`
   ```
   原始：postgresql://user:pass@host:5432/db
   修改：postgresql+asyncpg://user:pass@host:5432/db
   ```

### 3.3 啟用 pgvector 擴充

1. 在 Zeabur 的 PostgreSQL 服務頁面，找到 **Connect** 或 **Terminal**
2. 執行以下 SQL：
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   （如果 Zeabur 不支援直接執行 SQL，別擔心，程式啟動時會自動嘗試建立）

### 3.4 部署 FriendKeeper API

1. 在專案中點擊 **Add Service** → **Git**
2. 連結你的 GitHub，選擇 `friendkeeper` Repository
3. Zeabur 會自動偵測 Dockerfile 並開始建構
4. 等待建構完成（第一次會比較久，因為要下載 InsightFace 模型，大約 5-10 分鐘）

### 3.5 設定網域

1. 點進 FriendKeeper API 服務
2. 在 **Networking** 頁面，點擊 **Generate Domain**
3. 你會得到一個網址，例如 `friendkeeper-xxxx.zeabur.app`
4. **記下這個網址**，稍後設定 n8n 時會用到

---

## 步驟 4：設定環境變數

在 Zeabur 的 FriendKeeper API 服務中，進入 **Variables** 頁面，新增以下環境變數：

| 變數名稱 | 值 | 說明 |
|---------|---|------|
| `TELEGRAM_BOT_TOKEN` | 步驟 1 的 Token | Telegram Bot Token |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 步驟 1 的 Chat ID | 你的 Chat ID |
| `DATABASE_URL` | 步驟 3.2 修改後的連線字串 | 資料庫連線 |
| `OPENAI_API_KEY` | 你的 OpenAI API Key | 場景描述用 |
| `FACE_SIMILARITY_THRESHOLD` | `0.6` | 人臉相似度閾值 |
| `UPLOAD_DIR` | `/app/uploads` | 照片儲存路徑 |

設定完成後，Zeabur 會自動重新部署服務。

### 驗證部署

打開瀏覽器，訪問 `https://你的網域/docs`，應該能看到 FastAPI 的 Swagger 文件頁面。

---

## 步驟 5：設定 n8n 工作流

### 5.1 在 n8n 設定 Telegram 憑證

1. 進入你的 n8n
2. 到 **Credentials** → **Add Credential**
3. 搜尋 **Telegram**，選擇 **Telegram API**
4. 在 **Access Token** 欄位貼上步驟 1 的 Bot Token
5. 儲存

### 5.2 匯入照片處理工作流

1. 在 n8n 點擊 **Add Workflow** → **Import from File**
2. 選擇 `n8n/workflow_photo_processing.json`
3. 匯入後需要修改以下設定：

   **所有 Telegram 節點：**
   - 選擇剛才建立的 Telegram 憑證

   **「呼叫人臉辨識 API」節點：**
   - 把 URL 中的 `YOUR_FASTAPI_URL` 改為你的 Zeabur 網域
   - 例如：`https://friendkeeper-xxxx.zeabur.app/api/v1/process-photo`

   **「處理 Bot 指令」節點：**
   - 同樣把 `YOUR_FASTAPI_URL` 改為你的 Zeabur 網域

4. 儲存並啟用工作流

### 5.3 匯入每日提醒工作流

1. 同樣匯入 `n8n/workflow_daily_reminder.json`
2. 修改設定：

   **「取得今日提醒」節點：**
   - 把 `YOUR_FASTAPI_URL` 改為你的 Zeabur 網域

   **「發送提醒」節點：**
   - 選擇 Telegram 憑證
   - 把 `YOUR_CHAT_ID` 改為你的 Chat ID

3. 儲存並啟用工作流

---

## 🎉 部署完成！

現在可以開始使用了：

### 測試步驟

1. 在 Telegram 找到你的 Bot，發送 `/help` → 應該收到指令說明
2. 發送 `/new 測試人` → 建立測試聯絡人
3. 拍一張自拍，傳給 Bot → Bot 會回覆「未能辨識」（因為還沒註冊人臉）
4. 使用 Swagger 文件（`/docs`）手動呼叫 `/api/v1/faces/register` 來註冊人臉
5. 再傳一張照片 → 應該能辨識出來了！

### 註冊人臉的替代方式

目前註冊人臉需要透過 API，未來可以加上 Telegram 的互動流程。
在 Swagger 文件頁面操作方式：

1. 開啟 `https://你的網域/docs`
2. 找到 `POST /api/v1/faces/register`
3. 點 **Try it out**
4. 上傳照片，填入 contact_id（從 `/api/v1/contacts` 查詢）
5. 執行

---

## 常見問題

### Q: 建構失敗怎麼辦？
A: 檢查 Zeabur 的建構日誌，最常見的問題是記憶體不足。InsightFace 模型需要較多記憶體，建議使用至少 1GB RAM 的方案。

### Q: 人臉辨識不準確？
A: 每位聯絡人建議註冊 3-5 張不同角度、光線的照片。可以調整 `FACE_SIMILARITY_THRESHOLD` 環境變數（降低閾值更容易匹配，但可能有誤判）。

### Q: OpenAI 的費用大概多少？
A: GPT-4o 的 Vision 功能，使用 low detail 模式，每張照片約 $0.001-0.003 美元。每天傳 10 張照片，一個月大約 $1 以內。

### Q: 照片資料安全嗎？
A: 所有人臉辨識都在你自己的 Zeabur 容器中進行，不會傳到第三方。唯一的外部呼叫是 OpenAI（場景描述），如果不需要可以不設 OPENAI_API_KEY，系統會自動跳過。
