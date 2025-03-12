# 自傳問答與生成系統

## 功能
- 逐步問答收集自傳資料。
- 生成風格化、多語言自傳。
- 支援預覽、編輯和匯出（PDF/TXT）。

## 安裝
1. 安裝依賴：`pip install -r requirements.txt`
2. 配置 `.env`（見範例）。
3. 初始化資料庫：`python models/*.py`
4. 啟動：`python app.py`

## API
- `POST /auth/register`：註冊
- `GET /biography/next-question`：獲取下個問題
- `POST /biography/answer`：提交回答
- `POST /biography/generate`：生成自傳（帶 `style` 和 `language`）
- `GET /biography/preview`：預覽最新自傳
- `PUT /biography/edit`：編輯自傳
- `GET /biography/export/<id>`：匯出自傳

## 部署
- 使用 Gunicorn：`gunicorn -w 4 app:app`
- 配置 Nginx 反向代理。