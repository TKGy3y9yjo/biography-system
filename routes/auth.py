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
        data = request.get_json()
        if data is None:
            print("No JSON data received")  # 增加日誌
            return jsonify({"error": "No JSON data provided"}), 400
        email = data.get('email')
        password = data.get('password')
        print(f"Received email: {email}")  # 增加日誌
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        hashed_password = pbkdf2_sha256.hash(password)
        with ENGINE.connect() as conn:
            conn.execute(
                text("INSERT INTO users (email, password) VALUES (:email, :password)"),
                {"email": email, "password": hashed_password}
            )
            conn.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        print(f"Registration error: {str(e)}")  # 增加日誌
        if "UNIQUE constraint failed" in str(e):
            return jsonify({"error": "Email already exists"}), 409
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

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