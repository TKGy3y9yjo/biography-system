# 自傳問答與生成系統

## 概述

這是一個基於 Flask 的自傳問答與生成系統，允許用戶通過逐步回答問題來收集自傳資料，生成風格化、多語言的自傳，並支援預覽、編輯和匯出功能。系統使用 SQLite 資料庫儲存用戶資料、問題、回答和生成的自傳，並整合 OpenAI API 進行問題生成和自傳撰寫。

## 功能

- **動態問答**：根據用戶回答動態生成自傳相關問題，涵蓋童年、教育、職業、家庭和夢想等主題。
- **自傳生成**：根據用戶的問答資料生成約 500 字的自傳，支援多種風格（自然、正式、文藝）和語言（中文、英文）。
- **進度追蹤**：顯示用戶的問答進度，包括已回答問題數、總字數和完成百分比。
- **預覽與編輯**：允許用戶預覽生成的自傳並進行編輯。
- **版本管理**：儲存所有自傳版本，支援查看歷史記錄。
- **匯出功能**：支援將自傳匯出為 PDF 或 TXT 格式。
- **計劃選擇**：提供免費、進階和高級計劃，限制不同的字數上限。
- **用戶認證**：支援用戶註冊、登入和 JWT 認證。
- **效能優化**：使用連線池（SQLAlchemy）、快取（Flask-Caching）和 WAL 模式提升資料庫效能。
- **壓力測試**：已完成系統壓力測試，確保穩定性。

## 安裝

1. **安裝依賴**：

   ```bash
   pip install -r requirements.txt
   ```
2. **配置環境變數**： 創建 .env 檔案並填入以下內容：

   ```
   SECRET_KEY=your-secret-key
   OPENAI_API_KEY=your-openai-api-key
   DATABASE=database.db
   ```
3. **初始化資料庫**： 執行以下指令以創建必要的資料表：

   ```bash
   python models/user.py
   python models/plan.py
   python models/answer.py
   python models/biography.py
   ```
4. **啟動應用**：

   ```bash
   python app.py
   ```

## 功能 API

以下是系統的主要 API 端點：

- **認證**
  - POST /auth/register：用戶註冊，需提供 email 和 password。
  - POST /auth/login：用戶登入，返回 JWT token。
- **計劃管理**
  - GET /plans/plans：獲取所有可用計劃（免費、進階、高級）。
  - POST /plans/select-plan：為用戶選擇計劃。
- **問答與自傳生成**
  - GET /biography/next-question：獲取下一個自傳問題，根據用戶回答動態生成。
  - POST /biography/answer：提交問題回答並觸發新問題生成。
  - POST /biography/reset：重置用戶的問題和回答。
  - POST /biography/generate：根據問答資料生成自傳，支援指定風格和語言。
  - GET /biography/progress：查看問答進度和最新自傳。
  - GET /biography/preview：預覽最新自傳。
  - PUT /biography/edit：編輯指定自傳內容。
  - GET /biography/versions：列出所有自傳版本。
  - GET /biography/export/&lt;biography_id&gt;：匯出自傳（PDF 或 TXT 格式）。

## 資料庫結構

- **users**：儲存用戶資訊（id, email, password）。
- **plans**：儲存計劃資訊（id, name, word_limit）。
- **user_plans**：記錄用戶選擇的計劃（user_id, plan_id）。
- **questions**：儲存問題（user_id, content, question_order, theme, story_id）。
- **answers**：儲存回答（user_id, question_id, answer）。
- **biographies**：儲存生成的自傳（user_id, content, style, language, created_at）。

## 技術棧

- **後端**：Flask, SQLAlchemy, SQLite
- **認證**：JWT, PBKDF2-SHA256
- **AI 整合**：OpenAI API（GPT-3.5-turbo）
- **前端**：HTML, JavaScript（index.html）
- **匯出**：ReportLab（PDF 生成）
- **快取**：Flask-Caching
- **其他**：Dotenv（環境變數管理）

## 部署

1. 確保伺服器環境安裝 Python 3.8+ 和必要依賴。
2. 將專案複製到伺服器並配置 .env 檔案。
3. 使用 Gunicorn 或 uWSGI 作為 WSGI 伺服器：

   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
4. 配置 Nginx 或其他反向代理以處理靜態檔案和請求。
5. 啟用 HTTPS（推薦使用 Let’s Encrypt）。
6. 定期備份 SQLite 資料庫（database.db）。

## 注意事項

- 確保 OPENAI_API_KEY 正確配置，否則問題生成和自傳生成將失敗。
- SQLite WAL 模式已啟用，適合高並發讀寫場景，但需定期檢查資料庫完整性。
- JWT token 有效期為 24 小時，過期後需重新登入。
- 匯出 PDF 時需確保 ReportLab 正確安裝，且伺服器有足夠記憶體處理大型文件。

## 未來改進

- 新增多語言支援（日文、韓文等）。
- 實現更複雜的問題生成邏輯（例如基於情感分析）。
- 支援圖片上傳以豐富自傳內容。
- 提供自傳模板選擇功能。