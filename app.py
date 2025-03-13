from flask import Flask
import config
from routes.auth import auth_bp
from routes.plans import plans_bp
from routes.biography import biography_bp
from flask_caching import Cache
        
app = Flask(__name__)
app.secret_key = config.SECRET_KEY
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'}) 

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(plans_bp, url_prefix='/plans')
app.register_blueprint(biography_bp, url_prefix='/biography')

@app.route('/')
def hello():
    return "Welcome to Biography System!"

if __name__ == "__main__":
    app.run(debug=True)