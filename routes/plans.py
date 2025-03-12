from flask import Blueprint, jsonify,request
import sqlite3
import config
import jwt
from functools import wraps
plans_bp = Blueprint('plans', __name__)

@plans_bp.route('/test')
def test():
    return "Plans route works!"
# routes/plans.py
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({"error": "Token is missing"}), 401
        try:
            token = token.split(" ")[1]
            payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
            request.user_id = payload['user_id']  # 將 user_id 存到 request 中
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorator

plans_bp = Blueprint('plans', __name__)

@plans_bp.route('/plans', methods=['GET'])
@token_required
def get_plans():
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, word_limit FROM plans")
    plans = [{"id": row[0], "name": row[1], "word_limit": row[2]} for row in cursor.fetchall()]
    conn.close()
    return jsonify({"plans": plans}), 200

@plans_bp.route('/select-plan', methods=['POST'])
@token_required
def select_plan():
    data = request.get_json()
    user_id = request.user_id  # 從 JWT 獲取
    plan_id = data.get('plan_id')

    if not plan_id:
        return jsonify({"error": "Plan ID is required"}), 400
    data = request.get_json()

    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()

    # 檢查方案是否存在
    cursor.execute("SELECT id FROM plans WHERE id = ?", (plan_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Invalid plan ID"}), 404

    # 更新或插入用戶選擇
    cursor.execute("INSERT OR REPLACE INTO user_plans (user_id, plan_id) VALUES (?, ?)", 
                  (user_id, plan_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Plan selected successfully"}), 200





