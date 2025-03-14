# 自傳問答與生成系統


## 功能
- 逐步問答收集自傳資料。
- 生成風格化、多語言自傳。
- 支援預覽、編輯和匯出（PDF/TXT）。

## 新增功能 (Day 9)
- 效能優化（連線池、快取）。
- 壓力測試完成。

## 安裝
1. 安裝依賴：`pip install -r requirements.txt`
2. 配置 `.env`（見範例）。
    SECRET_KEY=your-secret-key
    OPENAI_API_KEY=your-openai-api-key
    DATABASE=database.db
3. 初始化資料庫：`python models/*.py`
4. 啟動：`python app.py`

## 功能 API
- 動態問題生成 (/next-question): 根據用戶回答生成下一個自傳問題。
- 回答提交 (/answer): 儲存用戶回答並觸發新問題生成。
- 自傳生成 (/generate): 根據問答資料生成約 500 字的自傳。
- 進度追蹤 (/progress): 顯示問題回答進度和最新自傳。
- 預覽與編輯 (/preview, /edit): 查看和修改生成的自傳。
- 版本管理 (/versions): 列出所有自傳版本。
- 匯出功能 (/export/<biography_id>): 支援 PDF 和 TXT 格式匯出自傳。

## 部署



