# routes/biography.py
from flask import Blueprint, jsonify, request,  send_file, Flask
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
import logging
from services.follow_up import get_next_question as ai_get_next_question, evaluate_answer

# 設置日誌


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

biography_bp = Blueprint('biography', __name__)
UPLOAD_FOLDER = 'static/uploads'

THEMES = ["童年", "教育", "職業", "家庭", "夢想"]
MAX_QUESTIONS_PER_THEME = 18  # 3 個故事 × 6 題
MAX_QUESTIONS_PER_STORY = 6

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


@biography_bp.route('/answer/image', methods=['POST'])
@token_required
def upload_image():
    user_id = request.user_id
    question_id = request.form.get('question_id')
    file = request.files.get('file')

    if not question_id or not file:
        return jsonify({"error": "缺少 question_id 或檔案"}), 400

    filename = f"{user_id}_{question_id}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    with ENGINE.connect() as conn:
        conn.execute(
            text("INSERT INTO answer_images (user_id, question_id, image_path) VALUES (:user_id, :question_id, :path)"),
            {"user_id": user_id, "question_id": question_id, "path": filepath}
        )
        conn.commit()
    return jsonify({"message": "圖片上傳成功", "path": filepath}), 200

@biography_bp.route('/answer', methods=['POST'])
@token_required
def submit_answer():
    """提交回答 → 回傳下一題。"""
    user_id = request.user_id
    data = request.get_json()
    question_id = data.get('question_id')
    answer = data.get('answer')

    if not question_id or not answer:
        return jsonify({"error": "Question ID and answer are required"}), 400
    
    with ENGINE.connect() as conn:
        row = conn.execute(
            text("""
                SELECT question_order, theme, story_id
                FROM questions
                WHERE id = :qid AND user_id = :uid
            """),
            {"qid": question_id, "uid": user_id}
        ).fetchone()
        if not row:
            return jsonify({"error": "Invalid question ID"}), 404
        current_order, current_theme, current_story_id = row
        next_order = current_order + 1
    
        # 儲存回答
        conn.execute(
            text("""INSERT INTO answers (user_id, question_id, answer)
                     VALUES (:uid, :qid, :ans)"""),
            {"uid": user_id, "qid": question_id, "ans": answer}
        )
        # 2) 取得同主題歷史回答（不含本題）
        history_rows = conn.execute(
            text("""
                SELECT a.answer
                FROM answers a
                JOIN questions q ON a.question_id = q.id
                WHERE a.user_id = :uid
                AND q.theme = :thm
                AND a.question_id <> :qid
                ORDER BY a.id
            """),
            {"uid": user_id, "thm": current_theme, "qid": question_id},
        ).fetchall()
        hist_texts = [r[0] for r in history_rows]

        # ③ 計算回答品質指標
        metrics = evaluate_answer(answer, hist_texts)

        # 4) 把分數寫回 answers
        conn.execute(
            text("""
                UPDATE answers SET
                    detail_score     = :d,
                    emotion_score    = :e,
                    reflection_score = :r,
                    redundancy       = :red,
                    length           = :l
                WHERE user_id = :uid
                AND question_id = :qid
            """),
            {
                "d":   metrics["detail_score"],
                "e":   metrics["emotion_score"],
                "r":   metrics["reflection_score"],
                "red": metrics["redundancy"],
                "l":   metrics["length"],
                "uid": user_id,
                "qid": question_id,
            },
        )

        # 取出當前問題資訊
        row = conn.execute(
            text("""SELECT question_order, theme, story_id
                     FROM questions
                     WHERE id = :qid AND user_id = :uid"""),
            {"qid": question_id, "uid": user_id}
        ).fetchone()
        if not row:
            return jsonify({"error": "Invalid question ID"}), 404
        current_order, current_theme, current_story_id = row
        next_order = current_order + 1

        # 取得本主題與本故事的已提問數
        total_theme_questions = conn.execute(
            text("""SELECT COUNT(*) FROM questions
                     WHERE user_id=:uid AND theme=:thm"""),
            {"uid": user_id, "thm": current_theme}
        ).fetchone()[0]
        total_story_questions = conn.execute(
            text("""SELECT COUNT(*) FROM questions
                     WHERE user_id=:uid AND theme=:thm AND story_id=:sid"""),
            {"uid": user_id, "thm": current_theme, "sid": current_story_id}
        ).fetchone()[0]

        # ------------------ 產生下一個問題 ------------------
        if total_story_questions < MAX_QUESTIONS_PER_STORY:
            # ① 撈歷史回答（同主題）
            history_rows = conn.execute(
                text("""SELECT a.answer FROM answers a
                         JOIN questions q ON a.question_id=q.id
                         WHERE a.user_id=:uid AND q.theme=:thm
                         ORDER BY q.question_order"""),
                {"uid": user_id, "thm": current_theme}
            ).fetchall()
            history_texts = [r[0] for r in history_rows if r[0]]

            # ② 呼叫智能追問模組
            next_question = ai_get_next_question(answer, current_theme, history_texts)
            next_story_id = current_story_id

        elif total_theme_questions < MAX_QUESTIONS_PER_THEME:
            # 開啟新故事（同主題）
            next_story_id = current_story_id + 1
            next_question = f"除了剛才提到的，關於你的{current_theme}還有什麼其他特別的經歷嗎？"
        else:
            # 切換主題或結束
            idx = THEMES.index(current_theme)
            if idx + 1 < len(THEMES):
                next_theme = THEMES[idx + 1]
                next_story_id = 1
                next_question = f"關於你的{next_theme}，有什麼特別的經歷嗎？"
                current_theme = next_theme  # 更新以便 insert
            else:
                conn.commit()
                return jsonify({"message": "All themes completed, ready for biography generation"}), 200

        # 插入下一題
        new_qid = conn.execute(
            text("""INSERT INTO questions
                     (user_id, content, question_order, theme, story_id)
                     VALUES (:uid, :cnt, :ord, :thm, :sid)
                     RETURNING id"""),
            {
                "uid": user_id,
                "cnt": next_question,
                "ord": next_order,
                "thm": current_theme,
                "sid": next_story_id,
            }
        ).fetchone()[0]
        conn.commit()

    return jsonify({
        "message": "Answer submitted, next question generated",
        "aqi": metrics["aqi"],
        "question": {
            "id": new_qid,
            "content": next_question,
            "question_order": next_order,
            "theme": current_theme,
            "story_id": next_story_id,
        }
    }), 200
@biography_bp.route('/answer/audio', methods=['POST'])
@token_required
def transcribe_audio():
    """上傳音訊回答 -> Whisper 轉錄 -> 儲存回答 -> 產生下一題"""
    user_id = request.user_id

    # 參數驗證
    if 'file' not in request.files:
        return jsonify({"error": "缺少音訊檔案"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "未選擇檔案"}), 400
    question_id = request.form.get('question_id')
    if not question_id:
        return jsonify({"error": "缺少 question_id"}), 400

    # 保存檔案
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # Whisper 轉錄
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        with open(filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="zh"
            )
        text = transcription.text
    except Exception as e:
        return jsonify({"error": f"轉錄失敗：{str(e)}"}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    # 寫入 answers，並重用 submit_answer 的邏輯以產生下一題
    with ENGINE.connect() as conn:
        conn.execute(
            text("INSERT INTO answers (user_id, question_id, answer) VALUES (:uid,:qid,:ans)"),
            {"uid": user_id, "qid": question_id, "ans": text},
        )
        conn.commit()

    # 直接重用 submit_answer 流程：手動呼叫內部函式
    # （避免重複寫邏輯，可考慮抽取共用函式）
    request.get_json = lambda: {"question_id": question_id, "answer": text}
    return submit_answer()
@biography_bp.route('/transcribe-only', methods=['POST'])
@token_required
def transcribe_only():
    user_id = request.user_id

    if 'file' not in request.files:
        return jsonify({"error": "缺少音訊檔案"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "未選擇檔案"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    try:
        with open(filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="zh"
            )
        text = transcription.text
    except Exception as e:
        return jsonify({"error": f"轉錄失敗：{str(e)}"}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    return jsonify({"transcription": text}), 200

@biography_bp.route('/generate', methods=['POST'])
@token_required
def generate_biography():
   
   user_id = request.user_id
   try:
       data = request.get_json()
       if not data:
           return jsonify({"error": "No JSON data provided"}), 400
           
       style = data.get('style', '自然')
       language = data.get('language', '中文')
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
                    SELECT q.theme, q.content AS question, a.answer, ai.image_path
                    FROM questions q
                    LEFT JOIN answers a ON q.id = a.question_id AND a.user_id = :user_id
                    LEFT JOIN answer_images ai ON ai.question_id = q.id AND ai.user_id = :user_id
                    WHERE q.user_id = :user_id
                    ORDER BY q.question_order
                """),
                {"user_id": user_id}
            )
           qa_data = []
           for row in result.fetchall():
                qa_data.append({
                    "theme": row[0],
                    "question": row[1],
                    "answer": row[2] or "未回答",
                    "image_path": row[3]  # 可能為 None
                })

           if not qa_data:
               return jsonify({"error": "No data available to generate biography"}), 400

           answer_count = sum(1 for qa in qa_data if qa["answer"] != "未回答")
           total_length = sum(len(qa["answer"]) for qa in qa_data if qa["answer"] != "未回答")
           if answer_count < 5 or total_length < 200:
               return jsonify({"error": "Insufficient data for biography generation"}), 400

           # 格式化問答資料為逐字稿
           qa_text = ""
           for qa in qa_data:
                qa_text += f"主題：{qa['theme']}\n問題：{qa['question']}\n回答：{qa['answer']}\n"
                if qa['image_path']:
                    fixed_path = qa["image_path"].replace("\\", "/")
                    print("修正後圖：", fixed_path)
                    qa_text += f"相關圖片：{fixed_path}\n"
                qa_text += "\n"


           # 新 prompt 格式
           prompt = f"{qa_text}\n根據這份逐字稿/素材，請幫我改寫成一篇自傳，風格為{style}，字數{length}以上，用途為{usage}明確，具備{emotion}的情感，內容需保留真實感與可讀性，目的是{aim}。如果有相關圖片路徑，請在適當段落中以 ![圖片說明](圖片路徑) 的 markdown 格式嵌入圖片。"

           try:
               client = OpenAI(api_key=config.OPENAI_API_KEY)
               response = client.chat.completions.create(
                   model="gpt-4o",
                   messages=[{"role": "user", "content": prompt}],
                   max_tokens=800,
                   temperature=0.9
               )
               biography_content = response.choices[0].message.content.strip()
           except Exception as e:
               logger.error(f"OpenAI API error: {str(e)}")
               return jsonify({"error": "Failed to generate biography with AI"}), 500
            
           now = datetime.now()
           result = conn.execute(
                text("""
                    INSERT INTO biographies (user_id, content, style, language, created_at)
                    VALUES (:user_id, :content, :style, :language, :created_at)
                    RETURNING id
                """),
                {
                    "user_id": user_id,
                    "content": biography_content,
                    "style": style,
                    "language": language,
                    "created_at": now
                }
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

   except Exception as e:
       logger.error(f"Generate biography error: {str(e)}")
       return jsonify({"error": f"Internal server error: {str(e)}"}), 500
       
@biography_bp.route("/next-question", methods=["GET"])
@token_required
def get_next_question():
    """
    前端每次重新整理頁面，都會打這支 API 來拿「當前應回答的最新問題」。
    若還沒有任何問題，就自動建立第一題。
    """
    user_id = request.user_id
    with ENGINE.connect() as conn:
        row = conn.execute(
            text("""
                SELECT q.id, q.content, q.theme, q.story_id, q.question_order
                FROM questions q
                WHERE q.user_id = :uid
                ORDER BY q.id DESC
                LIMIT 1
            """),
            {"uid": user_id}
        ).fetchone()

        # 若還沒出第一題→產生初始主題／問題
        if row is None:
            first_theme = THEMES[0]
            first_question = f"在你的{first_theme}中，你最難忘的回憶是什麼？"
            new_id = conn.execute(
                text("""
                    INSERT INTO questions (user_id, content, question_order, theme, story_id)
                    VALUES (:uid, :cnt, 1, :thm, 1)
                    RETURNING id
                """),
                {"uid": user_id, "cnt": first_question, "thm": first_theme},
            ).fetchone()[0]
            conn.commit()
            return jsonify({
                "question": {
                    "id": new_id,
                    "content": first_question,
                    "theme": first_theme,
                    "story_id": 1,
                    "question_order": 1,
                }
            })

        # 已有題目→直接回給前端
        qid, content, theme, story_id, order = row
        return jsonify({
            "question": {
                "id": qid,
                "content": content,
                "theme": theme,
                "story_id": story_id,
                "question_order": order,
            }
        })


@biography_bp.route('/progress', methods=['GET'])
@token_required
def get_progress():
    user_id = request.user_id
    with ENGINE.connect() as conn:
        answered = conn.execute(
            text("SELECT COUNT(*) FROM answers WHERE user_id=:uid"),
            {"uid": user_id}
        ).fetchone()[0]

        total_questions = len(THEMES) * MAX_QUESTIONS_PER_THEME
        theme_coverage = answered / total_questions if total_questions else 0

        avg_aqi = conn.execute(
            text("SELECT AVG((detail_score+emotion_score+reflection_score)/3) FROM answers "
                 "WHERE user_id=:uid"),
            {"uid": user_id}
        ).fetchone()[0] or 0

        total_length = conn.execute(
            text("SELECT COALESCE(SUM(length),0) FROM answers WHERE user_id=:uid"),
            {"uid": user_id}
        ).fetchone()[0]

    return jsonify({
        "answered": answered,
        "remaining": total_questions - answered,
        "theme_coverage": theme_coverage,
        "avg_aqi": avg_aqi,
        "total_length": total_length
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
    new_title = data.get('title')  # 加這一行

    if not biography_id or (not new_content and new_title is None):
        return jsonify({"error": "Biography ID and new content or title are required"}), 400

    update_fields = []
    params = {"biography_id": biography_id, "user_id": user_id}

    if new_content:
        update_fields.append("content = :content")
        params["content"] = new_content

    if new_title is not None:
        update_fields.append("title = :title")
        params["title"] = new_title

    with ENGINE.connect() as conn:
        result = conn.execute(
            text(f"UPDATE biographies SET {', '.join(update_fields)} WHERE id = :biography_id AND user_id = :user_id"),
            params
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
            text("SELECT id, title, style, language, created_at FROM biographies WHERE user_id = :user_id ORDER BY created_at DESC"),
            {"user_id": user_id}
        )

        versions = [{"id": row[0], "title": row[1], "style": row[2], "language": row[3], "created_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4])} for row in result.fetchall()]


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
    