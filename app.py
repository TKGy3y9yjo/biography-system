from flask import Flask, render_template
from flask_cors import CORS  # 導入 CORS
from flask_caching import Cache
import config
from routes.auth import auth_bp
from routes.plans import plans_bp
from routes.biography import biography_bp
from sqlalchemy.sql import text

print("OPENAI_API_KEY:", config.OPENAI_API_KEY)
# 初始化 Flask 應用
app = Flask(__name__, static_url_path='/static', static_folder='static')

# 配置 SECRET_KEY
app.config["SECRET_KEY"] = config.SECRET_KEY

# 初始化 CORS，允許特定來源
CORS(app, resources={r"/*": {"origins": ["http://localhost:5000", "http://127.0.0.1:5000"]}})

# 初始化快取
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# 註冊藍圖
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(plans_bp, url_prefix='/plans')
app.register_blueprint(biography_bp, url_prefix='/biography')

# 初始化資料庫
def setup_database():
    with config.ENGINE.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        print("WAL mode enabled")
setup_database()

@app.route('/')
def hello():
    return render_template('index.html')


if __name__ == "__main__":
    app.run(debug=True)