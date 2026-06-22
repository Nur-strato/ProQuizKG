# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_babel import Babel

# Инициализируем объекты СТРОГО чистыми (без передачи app!)
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()