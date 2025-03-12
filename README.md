# 自傳生成系統需求
## 功能
1. 登入
   - 註冊：email, password
   - 登入：返回 JWT token
2. 選擇方案
   - 方案：免費(500字)、進階(1000字)、高級(無限)
3. 自傳問答
   - 5-10 個固定問題，支援進度保存
4. 自傳生成
   - 基於 GPT API，依方案限制字數
5. 回饋
   - 返回文字，支援歷史紀錄

## API
- POST /register
- POST /login
- GET /plans
- POST /select-plan
- GET /questions
- POST /answers
- POST /generate
- GET /biography
- GET /history