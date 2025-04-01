from flask import Blueprint, request, jsonify
from passlib.hash import pbkdf2_sha256
import sqlite3
import config
import jwt
from datetime import datetime, timedelta
from config import ENGINE, SECRET_KEY
from sqlalchemy.sql import text

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()  # 嘗試解析 JSON
        if data is None:
            return jsonify({"error": "No JSON data provided"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to decode JSON: {str(e)}"}), 400

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    hashed_password = pbkdf2_sha256.hash(password)

    try:
        with ENGINE.connect() as conn:
            conn.execute(
                text("INSERT INTO users (email, password) VALUES (:email, :password)"),
                {"email": email, "password": hashed_password}
            )
            conn.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return jsonify({"error": "Email already exists"}), 409
        return jsonify({"error": "Registration failed"}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    with ENGINE.connect() as conn:
        result = conn.execute(
            text("SELECT id, password FROM users WHERE email = :email"),
            {"email": email}
        )
        user = result.fetchone()

    if user and pbkdf2_sha256.verify(password, user[1]):
        token = jwt.encode({
            'user_id': user[0],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"token": token}), 200
    else:
        return jsonify({"error": "Invalid email or password"}), 401