# routes/biography.py
from flask import Blueprint, jsonify, request,  send_file, Flask
import sqlite3
import config
import jwt
from functools import wraps
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import io
from config import ENGINE
from sqlalchemy.sql import text
from flask_caching import Cache
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
biography_bp = Blueprint('biography', __name__)

THEMES = ["童年", "教育", "職業", "家庭", "夢想"]
MAX_QUESTIONS_PER_THEME = 18  # 每個主題最多 6 個問題（3 個故事，每故事 2 問）
MAX_QUESTIONS_PER_STORY = 6  # 每個故事最多 2 個問題

def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({"error": "Token is missing"}), 401
        try:
            token = token.split(" ")[1]
            payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
            request.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorator

@biography_bp.route('/reset', methods=['POST'])
@token_required
def reset_questions():
    user_id = request.user_id
    try:
        with ENGINE.connect() as conn:
            # 刪除用戶的所有回答
            conn.execute(
                text("DELETE FROM answers WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            # 刪除用戶的所有問題
            conn.execute(
                text("DELETE FROM questions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.commit()
        return jsonify({"message": "Questions and answers reset successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to reset: {str(e)}"}), 500


@biography_bp.route('/next-question', methods=['GET'])
@token_required
def get_next_question():
    user_id = request.user_id
    with ENGINE.begin() as conn:
        # 檢查用戶問題數和當前主題
        result = conn.execute(
            text("SELECT theme, COUNT(*) FROM questions WHERE user_id = :user_id GROUP BY theme"),
            {"user_id": user_id}
        )
        theme_counts = dict(result.fetchall())

        if not theme_counts:  # 無問題，生成初始問題
            theme = THEMES[0]
            initial_question = "你的童年有哪些特別的回憶？"
            result = conn.execute(
                text("INSERT INTO questions (user_id, content, question_order, theme, story_id) VALUES (:user_id, :content, :question_order, :theme, :story_id) RETURNING id"),
                {"user_id": user_id, "content": initial_question, "question_order": 1, "theme": theme, "story_id": 1}
            )
            
            question_id = result.fetchone()[0]
            return jsonify({"question": {"id": question_id, "content": initial_question, "question_order": 1, "theme": theme, "story_id": 1}}), 200

        # 獲取最新問題
        result = conn.execute(
            text("SELECT theme, question_order, story_id FROM questions WHERE user_id = :user_id ORDER BY question_order DESC LIMIT 1"),
            {"user_id": user_id}
        )
        last_theme, last_order, last_story_id = result.fetchone()
        theme_count = theme_counts.get(last_theme, 0)

        # 檢查當前故事進度
        result = conn.execute(
            text("SELECT COUNT(*) FROM questions WHERE user_id = :user_id AND theme = :theme AND story_id = :story_id"),
            {"user_id": user_id, "theme": last_theme, "story_id": last_story_id}
        )
        story_count = result.fetchone()[0]

        if story_count < MAX_QUESTIONS_PER_STORY:  # 故事未結束，返回最新問題
            result = conn.execute(
                text("SELECT id, content, question_order, story_id FROM questions WHERE user_id = :user_id AND theme = :theme AND story_id = :story_id ORDER BY question_order DESC LIMIT 1"),
                {"user_id": user_id, "theme": last_theme, "story_id": last_story_id}
            )
            last_question = result.fetchone()
            return jsonify({"question": {"id": last_question[0], "content": last_question[1], "question_order": last_question[2], "theme": last_theme, "story_id": last_story_id}}), 200
        elif theme_count < MAX_QUESTIONS_PER_THEME:  # 開啟新故事
            next_story_id = last_story_id + 1
            next_order = last_order + 1
            next_question = f"除了剛才提到的，關於你的{last_theme}還有什麼其他特別的經歷嗎？"
            result = conn.execute(
                text("INSERT INTO questions (user_id, content, question_order, theme, story_id) VALUES (:user_id, :content, :question_order, :theme, :story_id) RETURNING id"),
                {"user_id": user_id, "content": next_question, "question_order": next_order, "theme": last_theme, "story_id": next_story_id}
            )
            
            question_id = result.fetchone()[0]
            return jsonify({"question": {"id": question_id, "content": next_question, "question_order": next_order, "theme": last_theme, "story_id": next_story_id}}), 200
        else:  # 主題結束，切換下個主題
            current_theme_index = THEMES.index(last_theme)
            if current_theme_index + 1 < len(THEMES):
                next_theme = THEMES[current_theme_index + 1]
                next_order = last_order + 1
                next_question = f"關於你的{next_theme}，有什麼特別的經歷嗎？"
                result = conn.execute(
                    text("INSERT INTO questions (user_id, content, question_order, theme, story_id) VALUES (:user_id, :content, :question_order, :theme, :story_id) RETURNING id"),
                    {"user_id": user_id, "content": next_question, "question_order": next_order, "theme": next_theme, "story_id": 1}
                )
                
                question_id = result.fetchone()[0]
                return jsonify({"question": {"id": question_id, "content": next_question, "question_order": next_order, "theme": next_theme, "story_id": 1}}), 200
            else:
                return jsonify({"message": "All themes completed, ready for biography generation"}), 200

@biography_bp.route('/answer', methods=['POST'])
@token_required
def submit_answer():
    user_id = request.user_id
    data = request.get_json()
    question_id = data.get('question_id')
    answer = data.get('answer')

    if not question_id or not answer:
        return jsonify({"error": "Question ID and answer are required"}), 400

    with ENGINE.connect() as conn:
        # 插入回答
        conn.execute(
            text("INSERT INTO answers (user_id, question_id, answer) VALUES (:user_id, :question_id, :answer)"),
            {"user_id": user_id, "question_id": question_id, "answer": answer}
        )

        # 驗證問題 ID 是否有效
        result = conn.execute(
            text("SELECT question_order, theme, story_id FROM questions WHERE id = :question_id AND user_id = :user_id"),
            {"question_id": question_id, "user_id": user_id}
        )
        question_data = result.fetchone()
        if not question_data:
            return jsonify({"error": "Invalid question ID"}), 404
        current_order, current_theme, current_story_id = question_data
        next_order = current_order + 1

        # 檢查完成度
        result = conn.execute(
            text("SELECT COUNT(*) FROM answers WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        answer_count = result.fetchone()[0]
        result = conn.execute(
            text("SELECT SUM(LENGTH(answer)) FROM answers WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        total_length = result.fetchone()[0] or 0

        if answer_count >= 10 and total_length >= 200:
            conn.commit()
            return jsonify({"message": "Enough data collected for biography generation"}), 200

        # 檢查當前故事和主題進度
        result = conn.execute(
            text("SELECT COUNT(*) FROM questions WHERE user_id = :user_id AND theme = :theme"),
            {"user_id": user_id, "theme": current_theme}
        )
        theme_question_count = result.fetchone()[0]
        result = conn.execute(
            text("SELECT COUNT(*) FROM questions WHERE user_id = :user_id AND theme = :theme AND story_id = :story_id"),
            {"user_id": user_id, "theme": current_theme, "story_id": current_story_id}
        )
        story_count = result.fetchone()[0]

        if story_count < MAX_QUESTIONS_PER_STORY:  # 深入當前故事
            client = OpenAI(api_key=config.OPENAI_API_KEY)
            prompt = f"根據以下回答生成下一個與'{current_theme}'相關的自傳問題，要求啟發性且與回答內容相關：\n回答：'{answer}'"
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.9
            )
            next_question = response.choices[0].message.content.strip()
            next_story_id = current_story_id
        elif theme_question_count < MAX_QUESTIONS_PER_THEME:  # 開啟新故事
            next_story_id = current_story_id + 1
            next_question = f"除了剛才提到的，關於你的{current_theme}還有什麼其他特別的經歷嗎？"
        else:  # 主題結束，切換下個主題
            current_theme_index = THEMES.index(current_theme)
            if current_theme_index + 1 < len(THEMES):
                next_theme = THEMES[current_theme_index + 1]
                next_question = f"關於你的{next_theme}，有什麼特別的經歷嗎？"
                next_story_id = 1
            else:
                conn.commit()
                return jsonify({"message": "All themes completed, ready for biography generation"}), 200

        # 插入下一個問題
        result = conn.execute(
            text("INSERT INTO questions (user_id, content, question_order, theme, story_id) VALUES (:user_id, :content, :question_order, :theme, :story_id) RETURNING id"),
            {"user_id": user_id, "content": next_question, "question_order": next_order, "theme": current_theme, "story_id": next_story_id}
        )
        question_id = result.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Answer submitted, next question generated", "question": {"id": question_id, "content": next_question, "question_order": next_order, "theme": current_theme, "story_id": next_story_id}}), 200

@biography_bp.route('/transcribe', methods=['POST'])
@token_required
def transcribe_audio():
    user_id = request.user_id

    # 檢查音訊檔案
    if 'file' not in request.files:
        return jsonify({"error": "缺少音訊檔案"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "未選擇檔案"}), 400

    # 檢查 question_id
    question_id = request.form.get('question_id')
    if not question_id:
        return jsonify({"error": "缺少 question_id"}), 400

    # 保存音訊檔案
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # 初始化 OpenAI 客戶端
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    # 轉錄音訊
    try:
        with open(filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        text = transcription.text
    except Exception as e:
        return jsonify({"error": f"轉錄失敗：{str(e)}"}), 500
    finally:
        # 清理檔案（可選）
        if os.path.exists(filepath):
            os.remove(filepath)

    # 儲存回答到 answers 表
    try:
        with ENGINE.connect() as conn:
            conn.execute(
                text("INSERT INTO answers (user_id, question_id, answer) VALUES (:user_id, :question_id, :answer)"),
                {"user_id": user_id, "question_id": question_id, "answer": text}
            )
            conn.commit()
    except Exception as e:
        return jsonify({"error": f"儲存回答失敗：{str(e)}"}), 500

    # 檢查是否需要生成下一個問題（與 /biography/answer 邏輯一致）
    with ENGINE.connect() as conn:
        result = conn.execute(
            text("SELECT question_order, theme, story_id FROM questions WHERE id = :question_id AND user_id = :user_id"),
            {"question_id": question_id, "user_id": user_id}
        )
        question_data = result.fetchone()
        if not question_data:
            return jsonify({"error": "無效的 question_id"}), 404
        current_order, current_theme, current_story_id = question_data
        next_order = current_order + 1

        # 檢查回答數量和字數
        result = conn.execute(
            text("SELECT COUNT(*) FROM answers WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        answer_count = result.fetchone()[0]
        result = conn.execute(
            text("SELECT SUM(LENGTH(answer)) FROM answers WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        total_length = result.fetchone()[0] or 0

        if answer_count >= 10 and total_length >= 200:
            conn.commit()
            return jsonify({"message": "音訊回答已儲存，足夠資料可生成自傳", "transcription": text}), 200

        # 生成下一個問題（重用 /biography/answer 的邏輯）
        result = conn.execute(
            text("SELECT COUNT(*) FROM questions WHERE user_id = :user_id AND theme = :theme"),
            {"user_id": user_id, "theme": current_theme}
        )
        theme_question_count = result.fetchone()[0]
        result = conn.execute(
            text("SELECT COUNT(*) FROM questions WHERE user_id = :user_id AND theme = :theme AND story_id = :story_id"),
            {"user_id": user_id, "theme": current_theme, "story_id": current_story_id}
        )
        story_count = result.fetchone()[0]

        if story_count < MAX_QUESTIONS_PER_STORY:
            prompt = f"根據以下回答生成下一個與'{current_theme}'相關的自傳問題，要求啟發性且與回答內容相關：\n回答：'{text}'"
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.9
            )
            next_question = response.choices[0].message.content.strip()
            next_story_id = current_story_id
        elif theme_question_count < MAX_QUESTIONS_PER_THEME:
            next_story_id = current_story_id + 1
            next_question = f"除了剛才提到的，關於你的{current_theme}還有什麼其他特別的經歷嗎？"
        else:
            current_theme_index = THEMES.index(current_theme)
            if current_theme_index + 1 < len(THEMES):
                next_theme = THEMES[current_theme_index + 1]
                next_question = f"關於你的{next_theme}，有什麼特別的經歷嗎？"
                next_story_id = 1
            else:
                conn.commit()
                return jsonify({"message": "音訊回答已儲存，所有主題完成，可生成自傳", "transcription": text}), 200

        result = conn.execute(
            text("INSERT INTO questions (user_id, content, question_order, theme, story_id) VALUES (:user_id, :content, :question_order, :theme, :story_id) RETURNING id"),
            {"user_id": user_id, "content": next_question, "question_order": next_order, "theme": current_theme, "story_id": next_story_id}
        )
        question_id = result.fetchone()[0]
        conn.commit()

    return jsonify({
        "message": "音訊回答已儲存，下一個問題已生成",
        "transcription": text,
        "question": {"id": question_id, "content": next_question, "question_order": next_order, "theme": current_theme, "story_id": next_story_id}
    }), 200
    
@biography_bp.route('/generate', methods=['POST'])
@token_required
def generate_biography():
    user_id = request.user_id
    data = request.get_json()
    style = data.get('style', '自然')
    language = data.get('language', '中文')
    # 新增參數，預設值可根據需求調整
    length = data.get('length', '500 字')
    usage = data.get('usage', '個人紀錄')
    emotion = data.get('emotion', '積極')
    aim = data.get('aim', '展示個人經歷')

    with ENGINE.connect() as conn:
        result = conn.execute(
            text("SELECT theme, COUNT(*) FROM questions WHERE user_id = :user_id GROUP BY theme"),
            {"user_id": user_id}
        )
        theme_counts = dict(result.fetchall())

        result = conn.execute(
            text("""
                SELECT q.theme, q.content, a.answer
                FROM questions q
                LEFT JOIN answers a ON q.id = a.question_id AND a.user_id = :user_id
                WHERE q.user_id = :user_id
                ORDER BY q.question_order
            """),
            {"user_id": user_id}
        )
        qa_data = [{"theme": row[0], "question": row[1], "answer": row[2] or "未回答"} for row in result.fetchall()]

        if not qa_data:
            return jsonify({"error": "No data available to generate biography"}), 400

        answer_count = sum(1 for qa in qa_data if qa["answer"] != "未回答")
        total_length = sum(len(qa["answer"]) for qa in qa_data if qa["answer"] != "未回答")
        if answer_count < 10 or total_length < 200:
            return jsonify({"error": "Insufficient data for biography generation"}), 400

        # 格式化問答資料為逐字稿
        text = ""
        for qa in qa_data:
            text += f"主題：{qa['theme']}\n問題：{qa['question']}\n回答：{qa['answer']}\n\n"

        # 新 prompt 格式
        prompt = f"{text}\n根據這份逐字稿/素材，請幫我改寫成一篇自傳，風格為{style}，字數{length}以上，用途為{usage}明確，具備{emotion}的情感，內容需保留真實感與可讀性，目的是{aim}"

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,  # 增加 max_tokens 以支援更長的生成
            temperature=0.9
        )
        biography_content = response.choices[0].message.content.strip()

        result = conn.execute(
            text("INSERT INTO biographies (user_id, content, style, language) VALUES (:user_id, :content, :style, :language) RETURNING id"),
            {"user_id": user_id, "content": biography_content, "style": style, "language": language}
        )
        biography_id = result.fetchone()[0]
        conn.commit()

        return jsonify({
            "biography": {
                "id": biography_id,
                "content": biography_content,
                "style": style,
                "language": language,
                "created_at": datetime.now().isoformat()
            }
        }), 200

@biography_bp.route('/progress', methods=['GET'])
@token_required
@cache.cached(timeout=60)  # 快取 60 秒
def get_progress():
    user_id = request.user_id
    with ENGINE.connect() as conn:
        # 檢查主題計數（可選，若不需要可移除）
        result = conn.execute(
            text("SELECT theme, COUNT(*) FROM questions WHERE user_id = :user_id GROUP BY theme"),
            {"user_id": user_id}
        )
        theme_counts = dict(result.fetchall())

        # 獲取問題與回答進度
        result = conn.execute(
            text("""
                SELECT q.id, q.content, q.question_order, q.theme, q.story_id, a.answer
                FROM questions q
                LEFT JOIN answers a ON q.id = a.question_id AND a.user_id = :user_id
                WHERE q.user_id = :user_id
                ORDER BY q.question_order
            """),
            {"user_id": user_id}
        )
        progress = [{"id": row[0], "content": row[1], "question_order": row[2], "theme": row[3], "story_id": row[4], "answer": row[5]} for row in result.fetchall()]

        total_questions = len(progress)
        answered_questions = sum(1 for p in progress if p['answer'] is not None)
        total_length = sum(len(p['answer']) for p in progress if p['answer'] is not None)

        # 獲取最新自傳
        result = conn.execute(
            text("SELECT id, content, style, created_at FROM biographies WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1"),
            {"user_id": user_id}
        )
        biography = result.fetchone()
        biography_data = {"id": biography[0], "content": biography[1], "style": biography[2], "created_at": str(biography[3])} if biography else None

        return jsonify({
            "progress": progress,
            "total_questions": total_questions,
            "answered_questions": answered_questions,
            "total_length": total_length,
            "completion_percentage": (answered_questions / total_questions * 100) if total_questions > 0 else 0,
            "biography": biography_data
        }), 200

@biography_bp.route('/preview', methods=['GET'])
@token_required
def preview_biography():
    user_id = request.user_id
    with ENGINE.connect() as conn:
        # 獲取最新自傳
        result = conn.execute(
            text("SELECT id, content, style, created_at FROM biographies WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1"),
            {"user_id": user_id}
        )
        biography = result.fetchone()
        if not biography:
            return jsonify({"error": "No biography generated yet"}), 404

        return jsonify({
            "biography": {
                "id": biography[0],
                "content": biography[1],
                "style": biography[2],
                "created_at": str(biography[3])  # 轉為字串以確保 JSON 序列化
            }
        }), 200

@biography_bp.route('/edit', methods=['PUT'])
@token_required
def edit_biography():
    user_id = request.user_id
    data = request.get_json()
    biography_id = data.get('biography_id')
    new_content = data.get('content')

    if not biography_id or not new_content:
        return jsonify({"error": "Biography ID and new content are required"}), 400

    with ENGINE.connect() as conn:
        # 更新自傳內容
        result = conn.execute(
            text("UPDATE biographies SET content = :content WHERE id = :biography_id AND user_id = :user_id"),
            {"content": new_content, "biography_id": biography_id, "user_id": user_id}
        )
        if result.rowcount == 0:
            return jsonify({"error": "Biography not found or unauthorized"}), 404

        conn.commit()
        return jsonify({"message": "Biography updated successfully"}), 200
    
@biography_bp.route('/versions', methods=['GET'])
@token_required
def list_biography_versions():
    user_id = request.user_id
    with ENGINE.connect() as conn:
        # 獲取所有自傳版本
        result = conn.execute(
            text("SELECT id, style, language, created_at FROM biographies WHERE user_id = :user_id ORDER BY created_at DESC"),
            {"user_id": user_id}
        )
        versions = [{"id": row[0], "style": row[1], "language": row[2], "created_at": str(row[3])} for row in result.fetchall()]

        if not versions:
            return jsonify({"error": "No biographies found"}), 404

        return jsonify({"versions": versions}), 200

@biography_bp.route('/export/<int:biography_id>', methods=['GET'])
@token_required
def export_biography(biography_id):
    user_id = request.user_id
    format = request.args.get('format', 'pdf')  # 預設 PDF，可選 'txt'

    with ENGINE.connect() as conn:
        # 獲取指定自傳
        result = conn.execute(
            text("SELECT content, style, language FROM biographies WHERE id = :biography_id AND user_id = :user_id"),
            {"biography_id": biography_id, "user_id": user_id}
        )
        biography = result.fetchone()
        if not biography:
            return jsonify({"error": "Biography not found or unauthorized"}), 404

        content, style, language = biography
        filename = f"biography_{biography_id}_{style}_{language}"

        if format == 'pdf':
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = [Paragraph(content.replace('\n', '<br/>'), styles['Normal'])]
            doc.build(story)
            buffer.seek(0)
            return send_file(buffer, as_attachment=True, download_name=f"{filename}.pdf", mimetype='application/pdf')
        elif format == 'txt':
            buffer = io.BytesIO(content.encode('utf-8'))
            buffer.seek(0)
            return send_file(buffer, as_attachment=True, download_name=f"{filename}.txt", mimetype='text/plain')
        else:
            return jsonify({"error": "Unsupported format"}), 400