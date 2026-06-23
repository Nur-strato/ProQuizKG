import os
from datetime import datetime
from flask import Flask, render_template, session, request, redirect, url_for, abort
from flask_babel import Babel, _
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from flask_login import login_required, current_user
from functools import wraps

# 1. Импортируем ТОЛЬКО расширения
from extensions import db, migrate, login_manager, babel

load_dotenv()

app = Flask(__name__)

# === НАСТРОЙКА ЯЗЫКОВЫХ СЛОВАРЕЙ (BABEL) ===
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'ru', 'ky']
app.jinja_env.globals.update(_=_)


def get_locale():
    if 'lang' in session:
        return session['lang']
    return request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])


babel.init_app(app, locale_selector=get_locale)

# Конфигурация Базы Данных
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-local-only')
raw_uri = os.environ.get('DATABASE_URL', 'sqlite:///app.db')

if raw_uri.startswith("postgres://"):
    uri = raw_uri.replace("postgres://", "postgresql://", 1)
else:
    uri = raw_uri

if "postgresql" in uri and "sslmode" not in uri:
    if "?" in uri:
        uri += "&sslmode=require"
    else:
        uri += "?sslmode=require"

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация плагинов
db.init_app(app)
migrate.init_app(app, db)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# 2. ИМПОРТИРУЕМ МОДЕЛИ СТРОГО ПОСЛЕ ИНИЦИАЛИЗАЦИИ DB
from models import User, University, Tournament, PredictionBet


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# РЕГИСТРАЦИЯ БЛУПРИНТОВ — ТЕПЕРЬ ВСЕ СТРОГО ТУТ (ПОСЛЕ ИНИЦИАЛИЗАЦИИ DB)
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.tournaments import tournaments_bp
from routes.predict import predict_bp

app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(tournaments_bp)
app.register_blueprint(predict_bp)


# === ДЕКОРАТОР РОЛЕЙ ===
def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.status != role and current_user.status != 'head':
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# --- БАЗОВЫЕ РОУТЫ ---
@app.route('/')
@app.route('/home')
def index():
    return render_template("home.html")


@app.route('/set-lang/<lang_code>')
def set_lang(lang_code):
    if lang_code in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang'] = lang_code
    return redirect(request.referrer or url_for('index'))


# === СТРАНИЦЫ ДЛЯ ПРОВЕРКИ ДОСТУПА ===
@app.route('/secret-head-panel')
@role_required('head')
def head_panel():
    return f"Привет, {current_user.name}! Ты зашел на панель HEAD. Доступно только тебе."


@app.route('/admin-panel')
@role_required('admin')
def admin_panel():
    return f"Привет, {current_user.name}! Ты зашел на панель ADMIN. Сюда может войти Nura и Nur."


# --- ФУНКЦИЯ ИНИЦИАЛИЗАЦИИ БАЗЫ ---
def init_database():
    try:
        db.create_all()

        # === ХАКИ МИГРАЦИЙ НА КОРНЮ ВЫПОЛНЯЮТСЯ СТРОГО НА SQLITE ===
        if "sqlite" in uri:
            from sqlalchemy import text
            try:
                db.session.execute(text("SELECT stage_id FROM prediction_bets LIMIT 1"))
            except Exception:
                db.session.rollback()
                print("[DATABASE HACK] Колонки не найдены в SQLite. Модифицируем prediction_bets...")

                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN stage_id INTEGER DEFAULT 2"))
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN team_1 VARCHAR(100)"))
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN team_2 VARCHAR(100)"))
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN team_3 VARCHAR(100)"))
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN team_4 VARCHAR(100)"))
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN is_correct BOOLEAN DEFAULT 0"))
                db.session.commit()
                print("[DATABASE HACK] Базовые поля подиума добавлены.")

            try:
                db.session.execute(text("SELECT date FROM prediction_bets LIMIT 1"))
            except Exception:
                db.session.rollback()
                print("[DATABASE HACK] Колонка 'date' отсутствует в SQLite. Накатываем фикс...")
                db.session.execute(text("ALTER TABLE prediction_bets ADD COLUMN date DATETIME"))
                db.session.commit()
                print("[DATABASE HACK] Колонка 'date' успешно добавлена в таблицу prediction_bets!")

        # === 🔥 ИСПРАВЛЕНО: Автоматическое создание ВСЕХ трех этапов сезона в БД на АНГЛИЙСКОМ языке ===
        if Tournament.query.count() == 0:
            stages_preset = [
                Tournament(
                    id=1,
                    title="University League 2026: PLAYOFFS",
                    text="The main student quiz tournament of the season! The first massive battle of the Main League. 16 teams fight for the right to get into the top 8.",
                    status="ongoing",
                    league_type="qualification",
                    teams_count=16,
                    date_str="5 – 25 April 2026",
                    bg_image="/static/img/uni2026.png",
                    team_format="Team Format (3 students)",
                    prize_pool="75 000"
                ),
                Tournament(
                    id=2,
                    title="University League 2026: PRE-FINAL",
                    text="The equator of the season. The tension doubles. Only the 8 strongest rosters meet in a face-to-face confrontation to reach the finals.",
                    status="upcoming",
                    league_type="promotion",
                    teams_count=8,
                    date_str="November 2026",
                    bg_image="/static/images/university_bg.jpg",
                    team_format="Team Format (3 students)",
                    prize_pool="150 000"
                ),
                Tournament(
                    id=3,
                    title="University League 2026: GRAND FINAL",
                    text="The culmination of the year. 4 absolute intellectual machines share the prize pool and the title of ProQuiz.ky champion.",
                    status="upcoming",
                    league_type="promotion",
                    teams_count=4,
                    date_str="December 2026",
                    bg_image="/static/images/university_bg.jpg",
                    team_format="Team Format (3 students)",
                    prize_pool="300 000"
                )
            ]
            for stage in stages_preset:
                db.session.add(stage)
            db.session.commit()
            print("🏆 All 3 League stages successfully initialized in English!")

        # === 🔥 ИСПРАВЛЕНО: Автоматическое создание ВУЗов строго на АНГЛИЙСКОМ языке ===
        if University.query.count() == 0:
            unis_preset = [
                University(id=1, name="AUCA", city="Bishkek",
                           description="American University of Central Asia", is_host=True),
                University(id=2, name="Salymbekov University", city="Bishkek",
                           description="Salymbekov International University", is_sponsor=True),
                University(id=3, name="KRSU", city="Bishkek",
                           description="Kyrgyz-Russian Slavic University")
            ]
            for uni in unis_preset:
                db.session.add(uni)
            db.session.commit()
            print("🏢 Default universities successfully initialized in English!")

        # Наш пресет 5 аккаунтов
        users_preset = {
            'Nur': ('head', 'nur123'),
            'Nura': ('admin', 'nura123'),
            'T1': ('user', 'password123'),
            'T2': ('user', 'password123'),
            'T3': ('user', 'password123')
        }

        for login_attr, (status_attr, password_attr) in users_preset.items():
            user = User.query.filter_by(login=login_attr).first()

            if not user:
                hashed_password = generate_password_hash(password_attr)
                new_user = User(
                    name=login_attr,
                    login=login_attr,
                    password=hashed_password,
                    status=status_attr
                )
                db.session.add(new_user)
                print(f"👤 Создан аккаунт: {login_attr} ({status_attr})")
            else:
                user.status = status_attr

        db.session.commit()
        print("🚀 База данных успешно синхронизирована! Все аккаунты на месте.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Ошибка инициализации базы: {e}")


# --- РЕГИСТРАЦИЯ ИНИЦИАЛИЗАЦИИ БАЗЫ ДЛЯ ВСЕХ СРЕД (И ДЛЯ GUNICORN ТОЖЕ) ---
with app.app_context():
    init_database()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
