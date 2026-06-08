import os
import secrets
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, url_for, request, flash, abort, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.file import FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from sqlalchemy.sql import func

load_dotenv()

app = Flask(__name__)

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
db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Жесткий список топиков квизов лиги для управления через Select
QUIZ_TOPICS = [
    "Общая эрудиция", "Мировая история", "География и страны",
    "Кинематограф", "Музыка и поп-культура", "IT и технологии",
    "Спорт и киберспорт", "Литература и арт", "Наука и природа",
    "Логика и головоломки", "Мемы и тренды"
]


# --- МОДЕРНОВАЯ МОДЕЛЬ ВОПРОСОВ ДЛЯ ПРАКТИКИ ---
class PracticeQuestion(db.Model):
    __tablename__ = 'practice_questions'

    id = db.Column(db.Integer, primary_key=True)
    theme = db.Column(db.String(50), nullable=False, index=True)  # logic, history, science и т.д.
    question_text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(255), nullable=False)
    explanation = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)  # Возможность временно скрыть вопрос
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Метод для автоматической сборки JSON для фронтенда"""
        return {
            'q': self.question_text,
            'a': self.answer,
            'e': self.explanation if self.explanation else "Разбор логики для данного вопроса не требуется."
        }


# ==========================================================================
# 1. МОДЕЛИ ДАННЫХ И СВЯЗУЮЩИЕ ТАБЛИЦЫ
# ==========================================================================

friendship = db.Table('friendship',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('friend_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('status', db.String(20), default='pending')
)


class University(db.Model):
    """Модель профилей университетов-участников"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_description = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(50), default='Бишкек')
    address = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    logo = db.Column(db.String(200), nullable=True)
    is_host = db.Column(db.Boolean, default=False)
    is_sponsor = db.Column(db.Boolean, default=False)
    website = db.Column(db.String(200), nullable=True)

    students = db.relationship('User', backref='uni_profile', lazy=True)

    def __repr__(self):
        return f'<University {self.name}>'


class User(db.Model, UserMixin):
    """Модель пользователей и организаторов (аккаунты лиги)"""
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), default='user')  # user, admin, head
    name = db.Column(db.String(50), nullable=False)
    avatar = db.Column(db.String(200), default='default.png')
    login = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey('university.id'), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    favorite_topic = db.Column(db.String(50), default='Не указан')
    participations = db.relationship('Participation', backref='user', lazy=True)

    friends_rel = db.relationship('User',
                                  secondary=friendship,
                                  primaryjoin=(friendship.c.user_id == id),
                                  secondaryjoin=(friendship.c.friend_id == id),
                                  backref=db.backref('befriended_by', lazy='dynamic'),
                                  lazy='dynamic'
                                  )

    def get_confirmed_friends(self):
        """Возвращает только тех, кто принял дружбу"""
        forward = db.session.query(User).join(friendship, friendship.c.friend_id == User.id).filter(
            friendship.c.user_id == self.id,
            friendship.c.status == 'accepted'
        ).all()
        return forward

    def get_pending_requests(self):
        """Входящие заявки, которые ждут подтверждения от текущего юзера"""
        return db.session.query(User).join(friendship, friendship.c.user_id == User.id).filter(
            friendship.c.friend_id == self.id,
            friendship.c.status == 'pending'
        ).all()

    def friendship_status_with(self, other_user_id):
        """Проверяет статус отношений с конкретным игроком"""
        row = db.session.query(friendship).filter(
            ((friendship.c.user_id == self.id) & (friendship.c.friend_id == other_user_id)) |
            ((friendship.c.user_id == other_user_id) & (friendship.c.friend_id == self.id))
        ).first()
        if not row:
            return None
        return row.status

    def __repr__(self):
        return f'<User {self.login}>'


class Tournament(db.Model):
    """Модель турниров (сохраняет кастомные параметры и состояние окон)"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    text = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    past = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='upcoming')  # upcoming, live, completed
    league_type = db.Column(db.String(20), default='additional')  # main, additional
    teams_count = db.Column(db.Integer, default=16)
    date_str = db.Column(db.String(50), nullable=True)
    language = db.Column(db.String(10), default='ru')

    participations = db.relationship('Participation', backref='tournament', cascade="all, delete-orphan")


class HallOfFame(db.Model):
    """Модель карточек Зала Славы лиги"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    season = db.Column(db.String(50), nullable=False)
    winner_name = db.Column(db.String(100), nullable=False)
    university = db.Column(db.String(100), nullable=False)
    top_text = db.Column(db.String(150), nullable=True)
    bottom_text = db.Column(db.String(150), nullable=True)


class Participation(db.Model):
    """Модель связей участия игроков, командной статистики и очков за квизы"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
    team_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, default=0)
    is_winner = db.Column(db.Boolean, default=False)
    team_password = db.Column(db.String(10), nullable=True)


# ==========================================================================
# 2. ФОРМЫ ВАЛИДАЦИИ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================================================

class RegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=50)])
    login = StringField('Login', validators=[DataRequired(), Length(min=2, max=20)])
    avatar = FileField('Avatar', validators=[FileAllowed(['jpg', 'png'])])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('password')])
    university = StringField('University')
    submit = SubmitField('Register')

    def validate_login(self, login):
        user = User.query.filter_by(login=login.data).first()
        if user:
            raise ValidationError("This login is currently in use")


class LoginForm(FlaskForm):
    login = StringField('Login', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Log in')


class TournamentRegistrationForm(FlaskForm):
    team = StringField('Team Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[DataRequired()])
    submit = SubmitField('Register')


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    os.makedirs(os.path.dirname(picture_path), exist_ok=True)
    form_picture.save(picture_path)
    return picture_fn


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================================================
# 3. МАРШРУТЫ СТАТИКИ И АДМИН-ПАНЕЛИ (ROUTES)
# ==========================================================================

@app.route('/api/practice/questions/<theme_key>')
def get_practice_questions(theme_key):
    valid_themes = ['logic', 'history', 'science', 'geography', 'culture', 'literature']
    if theme_key not in valid_themes:
        return jsonify({'error': 'Неверная категория вопросов'}), 400

    questions = PracticeQuestion.query.filter_by(theme=theme_key, is_active=True) \
        .order_by(func.random()) \
        .limit(10) \
        .all()

    if not questions:
        return jsonify([])

    return jsonify([q.to_dict() for q in questions])


# --- СТРАНИЦА КОНСТРУКТОРА И ДОБАВЛЕНИЯ ВОПРОСОВ ---
@app.route('/admin/practice/add', methods=['GET', 'POST'])
@login_required
def admin_add_practice_question():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    if request.method == 'POST':
        theme = request.form.get('theme')
        question_text = request.form.get('question_text', '').strip()
        answer = request.form.get('answer', '').strip()
        explanation = request.form.get('explanation', '').strip()

        if not theme or not question_text or not answer:
            flash("Ошибка: Заполните все обязательные поля формы!", "danger")
            return redirect(url_for('admin_add_practice_question'))

        try:
            new_q = PracticeQuestion(
                theme=theme,
                question_text=question_text,
                answer=answer,
                explanation=explanation if explanation else None
            )
            db.session.add(new_q)
            db.session.commit()
            flash("🎉 Вопрос успешно сохранен в базу данных Арены!", "success")
            return redirect(url_for('admin_add_practice_question'))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка сохранения: {e}", "danger")
            return redirect(url_for('admin_add_practice_question'))

    stats = {}
    themes_list = ['logic', 'history', 'science', 'geography', 'culture', 'literature']
    for t in themes_list:
        stats[t] = PracticeQuestion.query.filter_by(theme=t).count()

    total_count = PracticeQuestion.query.count()
    return render_template('admin_add_question.html', stats=stats, total_count=total_count)


# --- ОБНОВЛЕННЫЙ РЕЕСТР: ВЫВОД ВСЕХ ВОПРОСОВ (ЛОКАЛЬНЫЕ + СУБД) ---
@app.route('/admin/practice/questions')
@login_required
def admin_view_practice_questions():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    # Твоя жестко захардкоженная база (копия для админки)
    local_db = {
        'logic': [
            {'question_text': "В детективных романах ОН часто помогает скрыть следы...",
             'answer': "Бумажные салфетки / целлюлозная вата", 'explanation': "Салфетки стирают отпечатки...",
             'is_local': True},
            {'question_text': "Если А = 5, Б = 10, а их сумма умноженная на два равна 30...", 'answer': "25",
             'explanation': "(10 - 5) в квадрате = 5 * 5 = 25.", 'is_local': True},
            {'question_text': "Какое понятие в технике и медицине объединяет элемент трубопровода...",
             'answer': "Клапан", 'explanation': "Существуют механические клапаны...", 'is_local': True},
            {'question_text': "Какое логическое понятие связывает шахматного коня...", 'answer': "Скачок",
             'explanation': "Конь совершает скачок через фигуры...", 'is_local': True},
            {'question_text': "Продолжите астрономический ряд планет: Меркурий, Венера...", 'answer': "Марс",
             'explanation': "Классический порядок расположения планет...", 'is_local': True},
            {'question_text': "Какое базовое строительное изобретение позволило людям смотреть...", 'answer': "Окно",
             'explanation': "Окно — прозрачный элемент стены...", 'is_local': True},
            {'question_text': "Что, согласно классической народной метафоре, летает без крыльев...",
             'answer': "Туча / Облако", 'explanation': "Движение тучи имитирует полёт...", 'is_local': True},
            {'question_text': "Оно всегда находится прямо перед нами, детерминирует наши поступки...",
             'answer': "Будущее", 'explanation': "Философско-логическая концепция...", 'is_local': True},
            {'question_text': "Чем больше физического объема из неё извлекаешь...", 'answer': "Яма",
             'explanation': "Удаление грунта напрямую увеличивает...", 'is_local': True},
            {'question_text': "Назовите самый легкий и распространенный элемент таблицы...", 'answer': "Водород",
             'explanation': "Водород (H) имеет атомную массу 1...", 'is_local': True}
        ],
        'history': [
            {'question_text': "В каком году произошла знаменитая битва при Ватерлоо...", 'answer': "1815 год",
             'explanation': "Битва состоялась 18 июня 1815 года...", 'is_local': True},
            {'question_text': "Какая древняя цивилизация оставила после себя иероглифическое письмо...",
             'answer': "Древний Египет", 'explanation': "Египтяне возводили монументальные пирамиды...",
             'is_local': True},
            {'question_text': "Кто официально признан первым императором Римской Империи...",
             'answer': "Октавиан Август", 'explanation': "Внучатый племянник Гая Юлия Цезаря...", 'is_local': True},
            {'question_text': "Какой древнегреческий полис принято считать исторической родиной...", 'answer': "Афины",
             'explanation': "В Афинах была развернута система прямого голосования...", 'is_local': True},
            {'question_text': "Какая грандиозная битва Второй мировой войны считается коренным переломом...",
             'answer': "Сталинградская битва", 'explanation': "Окружение и разгром 6-й армии вермахта...",
             'is_local': True},
            {'question_text': "Кто руководитель испанской экспедиции, которая в 1492 году случайно...",
             'answer': "Христофор Колумб", 'explanation': "Мореплаватель искал западный торговый путь...",
             'is_local': True},
            {'text': "В каком островном европейском государстве произошла первая промышленная...",
             'question_text': "В каком островном европейском государстве произошла первая промышленная революция...",
             'answer': "Великобритания", 'explanation': "Изобретение паровых машин началось на фабриках...",
             'is_local': True},
            {'question_text': "Как звали советского космонавта, совершившего первый в истории...",
             'answer': "Юрий Гагарин", 'explanation': "12 апреля 1961 года корабль 'Восток-1'...", 'is_local': True},
            {'question_text': "Какая царская династия непрерывно правила Россией более 300 лет...",
             'answer': "Романовы", 'explanation': "Династия началась с венчания на царство Михаила...",
             'is_local': True},
            {'question_text': "Убийство какого политического деятеля в Сараево послужило официальным триггером...",
             'answer': "Эрцгерцог Franz Ferdinand",
             'explanation': "Австрийский наследник был застрелен сербским националистом...", 'is_local': True}
        ],
        'science': [
            {'question_text': "Какая планета Солнечной системы известна в астрономии как 'Красная планета'...",
             'answer': "Марс", 'explanation': "Поверхность Марса покрыта реголитом...", 'is_local': True},
            {'question_text': "Какая фундаментальная физическая сила удерживает космические тела...",
             'answer': "Гравитация", 'explanation': "Закон всемирного тяготения описывает притяжение...",
             'is_local': True},
            {'question_text': "Как называется биохимический процесс синтеза органических веществ...",
             'answer': "Фотосинтез", 'explanation': "Происходит в хлоропластах зеленых растений...", 'is_local': True},
            {'question_text': "Какое аллотропное углеродное вещество признано самым твердым природным минералом...",
             'answer': "Алмаз", 'explanation': "Имеет кристаллическую кубическую решетку и оценку 10 по шкале Мооса.",
             'is_local': True},
            {'question_text': "Какое числовое значение по шкале Цельсия соответствует понятию Абсолютного нуля...",
             'answer': "−273.15 °C",
             'explanation': "Нижняя точка, при которой полностью прекращается тепловое движение...", 'is_local': True},
            {'question_text': "Какая макромолекула двойной спирали кодирует и передает из поколения в поколение...",
             'answer': "ДНК", 'explanation': "Дезоксирибонуклеиновая кислота хранит последовательность нуклеотидов.",
             'is_local': True},
            {'question_text': "Какой газ химически доминирует по объему в составе атмосферного воздуха Земли?",
             'answer': "Азот", 'explanation': "Доля стабильного азота (N2) в воздухе составляет около 78%.",
             'is_local': True},
            {'question_text': "Какой физик-теоретик разработал Специальную и Общую теории относительности...",
             'answer': "Альберт Эйнштейн", 'explanation': "Эйнштейн доказал относительность времени...",
             'is_local': True},
            {'question_text': "Как в физике и химии называют наименьшую электронейтральную частицу вещества...",
             'answer': "Атом", 'explanation': "Атом состоит из положительного ядра и облака электронов.",
             'is_local': True},
            {'question_text': "Какой переходный металл обладает уникальным свойством оставаться жидким...",
             'answer': "Ртуть", 'explanation': "Ртуть (Hg) переходит в твердую фазу только при −39 °C.",
             'is_local': True}
        ],
        'geography': [
            {'question_text': "Какой океан является самым глубоким и масштабным по площади зеркала...",
             'answer': "Тихий океан",
             'explanation': "Его общая площадь превосходит совокупный размер всей земной суши.", 'is_local': True},
            {'question_text': "Какое современное суверенное государство занимает первое место в мире по площади...",
             'answer': "Россия", 'explanation': "Территория государства раскинулась на площади более 17.1 млн кв. км.",
             'is_local': True},
            {
                'question_text': "В какой высочайшей горной системе Азии расположена пиковая точка планеты — гора Эверест...",
                'answer': "Гималаи", 'explanation': "Массив Гималаев находится на границе Китая и Непала.",
                'is_local': True},
            {'question_text': "Какая южноамериканская водная артерия признана самой длинной, глубокой и полноводной...",
             'answer': "Амазонка", 'explanation': "Она обладает крупнейшим в мире речным бассейном...",
             'is_local': True},
            {'question_text': "Назовите столицу Японии, образующую крупнейшую городскую агломерацию мира.",
             'answer': "Токио", 'explanation': "Главный мегаполис Японского архипелага и мировой финансовый центр.",
             'is_local': True},
            {
                'question_text': "Какой обитаемый континент планеты официально является самым засушливым, низким и плоским?",
                'answer': "Австралия",
                'explanation': "Огромные площади материковой территории заняты пустынным ландшафтом.",
                'is_local': True},
            {'question_text': "Какое бессточное море-озеро Ближнего Востока имеет экстремальную соленость...",
             'answer': "Мертвое море", 'explanation': "Минерализация воды достигает 300–310 промилле.",
             'is_local': True},
            {
                'question_text': "Через пригороды какого европейского столичного мегаполиса условно прочерчена линия Нулевого меридиана?",
                'answer': "Лондон",
                'explanation': "Гринвичская обсерватория расположена в историческом районе Лондона.", 'is_local': True},
            {'question_text': "Какая великая африканская пустыня является крупнейшей жаркой пустыней земного шара?",
             'answer': "Сахара", 'explanation': "Её общая площадь превышает 9 миллионов квадратных километров.",
             'is_local': True},
            {
                'question_text': "Какое единственное федеративное государство на Земле занимает целый обособленный материк?",
                'answer': "Австралия",
                'explanation': "Австралийский Союз полностью администрирует территорию материка.", 'is_local': True}
        ],
        'culture': [
            {
                'question_text': "Какой британский кинорежиссер срежиссировал интеллектуальные блокбастеры 'Начало', 'Интерстеллар'...",
                'answer': "Кристофер Нолан",
                'explanation': "Постановщик знаменит нелинейным повествованием и минимизацией графики.",
                'is_local': True},
            {
                'question_text': "Какая рок-группа XX века записала культовую шестиминутную композицию 'Bohemian Rhapsody'?",
                'answer': "Queen", 'explanation': "Фредди Меркьюри соединил в треке оперу, балладу и тяжелый рок.",
                'is_local': True},
            {'question_text': "Какое живописное полотно Леонардо да Винчи, защищенное бронестеклом в Лувре...",
             'answer': "Мона Лиза", 'explanation': "Портрет Лизы Герардини, написанный в эпоху Высокого Возрождения.",
             'is_local': True},
            {
                'question_text': "Кто является автором эпической литературной трилогии высокого фэнтези 'Властелин Колец'?",
                'answer': "Дж. Р. Р. Толкин",
                'explanation': "Оксфордский лингвист, детально проработавший мифологию Арды.", 'is_local': True},
            {
                'question_text': "Какая дочерняя анимационная студия корпорации Disney создала 'Историю игрушек' и 'ВАЛЛ-И'?",
                'answer': "Pixar", 'explanation': "Студия совершила технологическую revolution в сфере CGI-анимации.",
                'is_local': True},
            {
                'question_text': "Какая американская поп-исполнительница удерживает статус рекордсменки продаж и титул 'Королевы поп-музыки'?",
                'answer': "Мадонна", 'explanation': "Признана самой успешной и влиятельной сольной певицей в истории.",
                'is_local': True},
            {'question_text': "Какой голливудский актёр исполнил роль эксцентричного капитана Джека Воробья?",
             'answer': "Джонни Депп", 'explanation': "Харизматичная игра Деппа превратила франшизу в мировой хит.",
             'is_local': True},
            {
                'question_text': "В какой фантастической медиафраншизе Джорджа Лукаса ключевыми элементами являются Сила, ситхи...",
                'answer': "Звёздные Войны",
                'explanation': "Грандиозная космоопера, навсегда изменившая мировую индустрию кино.", 'is_local': True},
            {
                'question_text': "В каком калифорнийском мегаполисе ежегодно разворачивается церемония награждения премии 'Оскар'?",
                'answer': "Лос-Анджелес", 'explanation': "Статуэтки вручаются в знаменитом театре 'Долби' в Голливуде.",
                'is_local': True},
            {
                'question_text': "Какая азиатская платформа ввела глобальный тренд на алгоритмические вертикальные короткие видео?",
                'answer': "TikTok",
                'explanation': "Разработка компании ByteDance, изменившая принципы потребления контента.",
                'is_local': True}
        ],
        'literature': [
            {
                'question_text': "Кто является автором первого в русской литературе реалистического романа в стихах 'Евгений Онегин'?",
                'answer': "Александр Пушкин",
                'explanation': "Произведение создавалось поэтом на протяжении более 7 лет...", 'is_local': True},
            {
                'question_text': "Какой английский классический драматург эпохи Возрождения создал трагедию 'Ромео и Джульетта'?",
                'answer': "Уильям Шекспир",
                'explanation': "Пьеса о вечной вражде семейных кланов и любви подростков написана в 1595 году.",
                'is_local': True},
            {'question_text': "Кто написал эпический четырёхтомный исторический роман-эпопею 'Война и мир'?",
             'answer': "Лев Толстой",
             'explanation': "Глубокое философское и психологическое описание жизни общества...", 'is_local': True},
            {
                'question_text': "Под каким известным псевдонимом публиковал книги Сэмюэл Клеменс, написавший историю Тома Сойера?",
                'answer': "Марк Твен",
                'explanation': "Фраза взята из лексикона лоцманов Миссисипи и означает безопасную глубину.",
                'is_local': True},
            {
                'question_text': "Кто создал знаменитый тоталитарный роман-антиутопию '1984', введя термин 'Министерство Правды'?",
                'answer': "Джордж Оруэлл",
                'explanation': "Книга служит жестким предупреждением против тоталитарных режимов.", 'is_local': True},
            {
                'question_text': "Какому великому флорентийскому поэту принадлежит загробное эпическое путешествие 'Божественная комедия'?",
                'answer': "Данте Алигьери",
                'explanation': "Произведение заложило фундамент современного итальянского языка.", 'is_local': True},
            {'question_text': "Какой британский врач-писатель подарил миру цикл рассказов о сыщике Шерлоке Холмсе?",
             'answer': "Артур Конан Дойл", 'explanation': "Дойл популяризировал дедуктивный метод в детективном жанре.",
             'is_local': True},
            {
                'question_text': "Какой классический психологический роман Фёдора Достоевского стартует с теории Раскольникова...",
                'answer': "Преступление и наказание",
                'explanation': "Глубокое исследование греха, раскаяния и духовного перерождения личности.",
                'is_local': True},
            {
                'question_text': "Какой французский профессиональный военный лётчик написал философскую сказку 'Маленький принц'?",
                'answer': "Антуан де Сент-Экзюпери",
                'explanation': "Повесть-аллегория учит ответственности за тех, кого мы приручили.", 'is_local': True},
            {'question_text': "Какая британская писательница создала фэнтези-вселенную о школе чародейства Хогвартс?",
             'answer': "Джоан Роулинг",
             'explanation': "История о Гарри Поттере стала самой продаваемой серией книг в истории.", 'is_local': True}
        ]
    }

    # Вытягиваем динамические вопросы из БД
    db_questions = PracticeQuestion.query.order_by(PracticeQuestion.created_at.asc()).all()

    # Результирующий словарь группировки
    grouped_questions = {t: [] for t in ['logic', 'history', 'science', 'geography', 'culture', 'literature']}

    # Загружаем сначала дефолтные вопросы в пул
    for theme, q_list in local_db.items():
        grouped_questions[theme] = list(q_list)

    # Дописываем снизу вопросы из СУБД (пометив, что их можно удалять/редактировать)
    for q in db_questions:
        if q.theme in grouped_questions:
            grouped_questions[q.theme].append({
                'id': q.id,
                'question_text': q.question_text,
                'answer': q.answer,
                'explanation': q.explanation if q.explanation else "Разбор не указан.",
                'created_at': q.created_at,
                'is_local': False
            })

    # Пересчитываем суммарные счетчики
    counts = {theme: len(lst) for theme, lst in grouped_questions.items()}
    total_count = sum(counts.values())

    return render_template(
        'admin_view_questions.html',
        grouped=grouped_questions,
        counts=counts,
        total_count=total_count
    )


# --- НОВЫЙ МАРШРУТ: РЕДАКТИРОВАНИЕ ВОПРОСА В СУБД ---
@app.route('/admin/practice/questions/<int:id>/edit', methods=['POST'])
@login_required
def admin_edit_practice_question(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    question = PracticeQuestion.query.get_or_404(id)

    question.question_text = request.form.get('question_text', '').strip()
    question.answer = request.form.get('answer', '').strip()
    question.explanation = request.form.get('explanation', '').strip()

    if not question.question_text or not question.answer:
        flash("Ошибка: Текст вопроса и правильный ответ не могут быть пустыми!", "danger")
        return redirect(url_for('admin_view_practice_questions'))

    try:
        db.session.commit()
        flash("🎉 Изменения вопроса успешно сохранены в СУБД Арены!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка изменения: {e}", "danger")

    return redirect(url_for('admin_view_practice_questions'))

@app.route('/admin/practice/questions/<int:id>/delete', methods=['POST'])
@login_required
def admin_delete_practice_question(id):  # Имя функции должно быть ТАКИМ
    if current_user.status not in ['admin', 'head']:
        abort(403)
    question = PracticeQuestion.query.get_or_404(id)
    try:
        db.session.delete(question)
        db.session.commit()
        flash("Вопрос успешно ликвидирован из базы данных.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка удаления: {e}", "danger")
    return redirect(url_for('admin_view_practice_questions'))


@app.route('/')
@app.route('/home')
def index():
    return render_template("home.html")


@app.route('/admin/init-db')
@login_required
def admin_init_db():
    if current_user.status != 'admin':
        abort(403)
    try:
        db.create_all()
        flash("All database tables have been created!")
    except Exception as e:
        flash(f"Error: {e}")
        return str(e)
    return redirect(url_for('admin'))


@app.route('/admin', methods=['POST', 'GET'])
@login_required
def admin():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    if request.method == 'POST':
        title = request.form['title']
        text = request.form['text']
        status = request.form.get('status', 'upcoming')
        is_past = True if status == 'past' else False

        max_id = db.session.query(func.max(Tournament.id)).scalar()

        if max_id is None or max_id < 3:
            next_id = 4
        else:
            next_id = max_id + 1

        tournament = Tournament(
            id=next_id,
            title=title,
            text=text,
            past=is_past,
            status=status,
            league_type='additional'
        )

        try:
            db.session.add(tournament)
            db.session.commit()
            flash("Tournament announcement created successfully!", "success")
        except Exception as e:
            db.session.rollback()
            return str(e)

        return redirect(url_for('tournaments'))

    return render_template("admin.html")


# ==========================================================================
# 4. МАРШРУТЫ ТУРНИРОВ
# ==========================================================================

@app.route('/tournaments')
def tournaments():
    current_season = "SEASON_01: INCEPTION"
    main_stages_presets = {
        1: {
            "name": "PLAYOFF STAGE",
            "teams_count": 16,
            "date": "Октябрь 2026",
            "status": "live",
            "league_type": "qualification",
            "desc": "Первая масштабная битва сезона Главной Лиги. 16 команд сражаются за право попасть в топ-8. Ошибки здесь стоят дорого."
        },
        2: {
            "name": "PRE-FINAL SHOWDOWN",
            "teams_count": 8,
            "date": "Ноябрь 2026",
            "status": "live",
            "league_type": "promotion",
            "desc": "Экватор сезона. Напряжение удваивается. Только 8 сильнейших составов сходятся в очном противостоянии за выход в финал."
        },
        3: {
            "name": "THE GRAND FINAL",
            "teams_count": 4,
            "date": "Декабрь 2026",
            "status": "live",
            "league_type": "promotion",
            "desc": "Кульминация года. 4 абсолютные интеллектуальные машины делят призовой фонд и титул чемпиона ProQuiz.kg."
        }
    }

    months_display = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
                      "Ноябрь", "Декабрь"]
    main_tournaments = []

    for s_id, preset in main_stages_presets.items():
        db_stage = Tournament.query.get(s_id)
        if db_stage:
            if db_stage.date:
                display_date = f"{months_display[db_stage.date.month - 1]} {db_stage.date.year}"
            else:
                display_date = db_stage.date_str if db_stage.date_str else preset["date"]

            main_tournaments.append({
                "id": db_stage.id,
                "name": db_stage.title,
                "teams_count": db_stage.teams_count if db_stage.teams_count else preset["teams_count"],
                "date": display_date,
                "status": db_stage.status if db_stage.status else preset["status"],
                "league_type": db_stage.league_type if db_stage.league_type else preset["league_type"],
                "is_main_league": True,
                "desc": db_stage.text
            })
        else:
            main_tournaments.append({
                "id": s_id,
                "name": preset["name"],
                "teams_count": preset["teams_count"],
                "date": preset["date"],
                "status": preset["status"],
                "league_type": preset["league_type"],
                "is_main_league": True,
                "desc": preset["desc"]
            })

    try:
        db_additional = Tournament.query.filter(Tournament.id > 3).all()
    except Exception:
        db_additional = []

    additional_tournaments = []
    for t in db_additional:
        if t.date:
            display_date = f"{months_display[t.date.month - 1]} {t.date.year}"
        else:
            display_date = t.date_str if t.date_str else 'Февраль 2027'

        additional_tournaments.append({
            "id": t.id,
            "name": t.title,
            "teams_count": getattr(t, 'teams_count', 10) if getattr(t, 'teams_count', None) else 10,
            "date": display_date,
            "status": t.status if getattr(t, 'status', None) else "upcoming",
            "league_type": t.league_type if t.league_type else "open",
            "is_main_league": False,
            "desc": t.text
        })

    tournaments_list = main_tournaments + additional_tournaments
    return render_template('tournaments.html', season=current_season, tournaments=tournaments_list)


@app.route('/tournaments/<int:id>/set_results', methods=['GET', 'POST'])
@login_required
def admin_set_results(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    tournament = Tournament.query.get_or_404(id)
    participants = Participation.query.filter_by(tournament_id=id).all()

    if request.method == 'POST':
        tournament.past = True
        tournament.status = 'completed'

        next_tournament_id = None
        if tournament.id == 1:
            next_tournament_id = 2
        elif tournament.id == 2:
            next_tournament_id = 3

        for p in participants:
            score_value = request.form.get(f'score_{p.id}')
            if score_value:
                p.score = int(score_value)

            is_advanced_or_winner = True if request.form.get(f'winner_{p.id}') else False
            p.is_winner = is_advanced_or_winner

            if is_advanced_or_winner and next_tournament_id:
                already_advanced = Participation.query.filter_by(
                    user_id=p.user_id,
                    tournament_id=next_tournament_id
                ).first()

                if not already_advanced:
                    advanced_participant = Participation(
                        user_id=p.user_id,
                        tournament_id=next_tournament_id,
                        email=p.email,
                        phone_number=p.phone_number,
                        team_name=p.team_name,
                        score=0,
                        is_winner=False
                    )
                    db.session.add(advanced_participant)

        try:
            db.session.commit()
            if next_tournament_id == 2:
                flash("Итоги сохранены! Топ-8 команд продвинуты в Pre-Final.", "success")
            elif next_tournament_id == 3:
                flash("Итоги сохранены! Топ-4 команд продвинуты в Grand Final.", "success")
            else:
                flash("Гранд-Финал закрыт! Абсолютный чемпион сезона зафиксирован.", "success")

            return redirect(url_for('tournament_results', id=tournament.id))
        except Exception as e:
            db.session.rollback()
            return f"Database Error: {e}"

    return render_template("admin_set_results.html", tournament=tournament, participants=participants)


@app.route('/tournaments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tournament(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    if id <= 3 and current_user.status != 'head':
        abort(403)

    tournament_item = Tournament.query.get(id)

    if not tournament_item and id <= 3:
        titles_map = {1: "PLAYOFF STAGE", 2: "PRE-FINAL SHOWDOWN", 3: "THE GRAND FINAL"}
        texts_map = {
            1: "Первая масштабная битва сезона Главной Лиги. 16 команд сражаются за право попасть в топ-8. Ошибки здесь стоят дорого.",
            2: "Экватор сезона. Напряжение удваивается. Только 8 сильнейших составов сходятся в очном противостоянии за выход в финал.",
            3: "Кульминация года. 4 absolute машины делят призовой фонд и титул чемпиона ProQuiz.kg."
        }
        default_regs = {1: "qualification", 2: "promotion", 3: "promotion"}
        mock_dates = {1: datetime(2026, 10, 15, 18, 0), 2: datetime(2026, 11, 15, 18, 0),
                      3: datetime(2026, 12, 15, 18, 0)}

        tournament_item = Tournament(
            id=id,
            title=titles_map.get(id, "MAIN STAGE"),
            text=texts_map.get(id, ""),
            status="live",
            league_type=default_regs.get(id, "promotion"),
            date=mock_dates.get(id),
            language="ru",
            past=False
        )
        db.session.add(tournament_item)
        db.session.commit()

    if not tournament_item:
        abort(404)

    if request.method == 'POST':
        title_value = request.form.get('title')
        text_value = request.form.get('text')

        if title_value and text_value:
            tournament_item.title = title_value
            tournament_item.text = text_value
            tournament_item.status = request.form.get('status')
            tournament_item.league_type = request.form.get('league_type')

            selected_languages = request.form.getlist('languages')
            if selected_languages:
                tournament_item.language = ",".join(selected_languages)
            else:
                tournament_item.language = "ru"

            if request.form.get('teams_count'):
                try:
                    tournament_item.teams_count = int(request.form.get('teams_count'))
                except ValueError:
                    tournament_item.teams_count = 16

            raw_date = request.form.get('exact_date')
            if raw_date and raw_date.strip() != "":
                try:
                    if 'T' in raw_date:
                        tournament_item.date = datetime.strptime(raw_date, '%Y-%m-%dT%H:%M')
                    else:
                        tournament_item.date = datetime.strptime(raw_date, '%Y-%m-%d')
                except ValueError:
                    pass
            else:
                tournament_item.date = None

            try:
                db.session.commit()
                flash("Tournament updated successfully!", "success")
                return redirect(url_for('tournament_detail', id=tournament_item.id))
            except Exception as e:
                db.session.rollback()
                return f"Database Error: {e}"

    return render_template("edit_tournament.html", tournament=tournament_item)


@app.route('/tournaments/<int:id>')
def tournament_detail(id):
    tournament_item = Tournament.query.get(id)

    if not tournament_item and id <= 3:
        titles_map = {1: "PLAYOFF STAGE", 2: "PRE-FINAL SHOWDOWN", 3: "THE GRAND FINAL"}
        texts_map = {
            1: "Первая масштабная битва сезона Главной Лиги. 16 команд сражаются за право попасть в топ-8.",
            2: "Экватор сезона. Напряжение удваивается. Только 8 сильнейших составов сходятся в очном противостоянии.",
            3: "Кульминация года. 4 absolute машины делят призовой фонд и титул чемпиона ProQuiz.kg."
        }
        default_regs = {1: "qualification", 2: "promotion", 3: "promotion"}
        mock_dates = {1: datetime(2026, 10, 15, 18, 0), 2: datetime(2026, 11, 15, 18, 0),
                      3: datetime(2026, 12, 15, 18, 0)}

        class MockTournament:
            def __init__(self, t_id, title, text, reg_type, dt_obj):
                self.id = t_id
                self.title = title
                self.text = text
                self.name = title
                self.status = "live"
                self.league_type = reg_type
                self.past = False
                self.teams_count = 16 if t_id == 1 else (8 if t_id == 2 else 4)
                self.date = dt_obj
                self.language = "ru"

        tournament_item = MockTournament(id, titles_map.get(id), texts_map.get(id), default_regs.get(id),
                                         mock_dates.get(id))

    if not tournament_item:
        abort(404)

    if tournament_item.date:
        js_date = tournament_item.date.strftime('%Y-%m-%dT%H:%M:%S')
    else:
        js_date = "2026-12-31T23:59:59"

    months_ru = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня", "Июля", "Августа", "Сентября", "Октября",
                 "Ноября", "Декабря"]

    if tournament_item.date:
        dt = tournament_item.date
        formatted_date_str = f"{dt.day} {months_ru[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M')}"
    elif hasattr(tournament_item, 'date_str') and tournament_item.date_str:
        formatted_date_str = tournament_item.date_str
    else:
        formatted_date_str = "Дата не назначена"

    return render_template(
        'tournament_detail.html',
        tournament=tournament_item,
        js_target_date=js_date,
        formatted_date_str=formatted_date_str
    )


@app.route('/tournaments/<int:id>/delete', methods=['POST'])
@login_required
def delete_tournament(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    tournament = Tournament.query.get_or_404(id)
    try:
        db.session.delete(tournament)
        db.session.commit()
        flash("Tournament deleted!", "success")
        return redirect(url_for('tournaments'))
    except Exception as e:
        db.session.rollback()
        return str(e)


@app.route('/tournaments/<int:id>/participants')
def tournament_participants(id):
    tournament_item = Tournament.query.get_or_404(id)
    all_participations = Participation.query.filter_by(tournament_id=id).all()

    grouped_teams = {}
    for p in all_participations:
        if p.team_name not in grouped_teams:
            grouped_teams[p.team_name] = {
                'name': p.team_name,
                'players': []
            }
        grouped_teams[p.team_name]['players'].append(p)

    return render_template(
        "tournament_participants.html",
        tournament=tournament_item,
        teams=grouped_teams.values()
    )


@app.route('/tournaments/<int:tournament_id>/team/<string:team_name>', methods=['GET', 'POST'])
@login_required
def team_profile(tournament_id, team_name):
    tournament_item = Tournament.query.get_or_404(tournament_id)
    team_members = Participation.query.filter_by(tournament_id=tournament_id, team_name=team_name).all()

    if not team_members:
        abort(404)

    captain_participation = min(team_members, key=lambda p: p.id)
    is_captain = (current_user.id == captain_participation.user_id)

    if request.method == 'POST':
        if not is_captain:
            abort(403)

        new_password = request.form.get('team_password', '').strip()

        if new_password and len(new_password) >= 4:
            for member in team_members:
                member.team_password = new_password
            db.session.commit()
            flash("PIN-код команды успешно обновлен капитаном!", "success")
        else:
            flash("PIN-код должен состоять минимум из 4 символов!", "danger")

        return redirect(request.url)

    return render_template(
        "team_profile.html",
        tournament=tournament_item,
        team_name=team_name,
        members=team_members,
        captain_id=captain_participation.user_id,
        is_captain=is_captain,
        current_pin=captain_participation.team_password
    )


@app.route('/tournaments/<int:id>/results')
def tournament_results(id):
    tournament_item = Tournament.query.get_or_404(id)
    participants = Participation.query.filter_by(tournament_id=id).order_by(Participation.score.desc()).all()
    return render_template("tournament_results.html", tournament=tournament_item, participants=participants)


@app.route('/tournaments/<int:id>/register', methods=['GET', 'POST'])
@login_required
def tournament_register(id):
    tournament_item = Tournament.query.get_or_404(id)

    if tournament_item.past:
        flash("Registration is closed for past tournaments.", "danger")
        return redirect(url_for('tournament_detail', id=tournament_item.id))

    if not current_user.university_id or not current_user.uni_profile:
        flash("Ошибка: Для регистрации на турнир необходимо указать ваш университет в профиле!", "danger")
        return redirect(url_for('edit_profile'))

    existing_participation = Participation.query.filter_by(
        user_id=current_user.id,
        tournament_id=id
    ).first()

    if existing_participation:
        return render_template("tournament_register.html", tournament=tournament_item, already_registered=True)

    user_uni_name = current_user.uni_profile.name
    if user_uni_name.upper() == 'AUCA':
        max_teams_allowed = 3
    elif user_uni_name == 'Salymbekov University':
        max_teams_allowed = 1
    else:
        max_teams_allowed = 2

    available_teams = []
    for team_num in range(1, max_teams_allowed + 1):
        team_identifier = f"{user_uni_name} - Team {team_num}"
        team_members = Participation.query.filter_by(tournament_id=id, team_name=team_identifier).all()
        players_count = len(team_members)
        existing_password = team_members[0].team_password if players_count > 0 else None

        if players_count < 3:
            available_teams.append({
                'name': team_identifier,
                'slots_left': 3 - players_count,
                'has_password': True if existing_password else False
            })

    if request.method == 'POST':
        selected_team = request.form.get('team_name')
        phone = request.form.get('phone_number', 'N/A')
        input_password = request.form.get('team_password', '').strip()

        if not selected_team:
            flash("Пожалуйста, выберите команду!", "danger")
            return redirect(request.url)

        team_members = Participation.query.filter_by(tournament_id=id, team_name=selected_team).all()
        current_count = len(team_members)

        if current_count >= 3:
            flash(f"Ошибка! Команда {selected_team} уже полностью заполнена (3/3).", "danger")
            return redirect(request.url)

        final_password = None
        if current_count == 0:
            if not input_password or len(input_password) < 3:
                flash("Вы первый в этой команде! Придумайте 3-значный PIN-код для защиты состава от рандомов.",
                      "danger")
                return redirect(request.url)
            final_password = input_password
        else:
            required_password = team_members[0].team_password
            if required_password and input_password != required_password:
                flash("Неверный PIN-код команды! Этот состав зарезервирован группой друзей.", "danger")
                return redirect(request.url)
            final_password = required_password

        participant = Participation(
            user_id=current_user.id,
            tournament_id=tournament_item.id,
            team_name=selected_team,
            email=getattr(current_user, 'email', f"{current_user.login}@proquiz.kg"),
            phone_number=phone,
            team_password=final_password
        )

        try:
            db.session.add(participant)
            db.session.commit()
            flash(f"Вы успешно зашли в состав {selected_team}!", "success")
            return redirect(url_for('tournament_detail', id=tournament_item.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка базы данных: {e}", "danger")
            return redirect(request.url)

    return render_template(
        "tournament_register.html",
        tournament=tournament_item,
        user_uni=user_uni_name,
        available_teams=available_teams
    )


@app.route('/tournaments/<int:id>/leave', methods=['POST'])
@login_required
def tournament_leave(id):
    participation = Participation.query.filter_by(user_id=current_user.id, tournament_id=id).first()

    if not participation:
        flash("Вы не зарегистрированы на этот турнир.", "danger")
        return redirect(url_for('my_profile'))

    if participation.tournament.past:
        flash("Нельзя покинуть команду прошедшего турнира!", "danger")
        return redirect(url_for('my_profile'))

    try:
        db.session.delete(participation)
        db.session.commit()
        flash("Вы успешно покинули команду. Слот освобожден для других участников.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при выходе из команды: {e}", "danger")

    return redirect(url_for('my_profile'))


# --- МАРШРУТЫ ЗАЛА СЛАВЫ ---

@app.route('/gallery')
def hall_of_fame():
    entries = HallOfFame.query.order_by(HallOfFame.id.desc()).all()
    return render_template("hall_of_fame.html", hof_entries=entries)


@app.route('/gallery/upload', methods=['POST'])
@login_required
def upload_hof_entry():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    file = request.files.get('photo')
    if file:
        filename = save_picture(file)
        new_entry = HallOfFame(
            filename=filename,
            season=request.form.get('season'),
            winner_name=request.form.get('winner_name'),
            university=request.form.get('university'),
            top_text=request.form.get('top_text'),
            bottom_text=request.form.get('bottom_text')
        )
        db.session.add(new_entry)
        db.session.commit()
        flash("Запись добавлена в Зал славы!")

    return redirect(url_for('hall_of_fame'))


@app.route('/gallery/delete/<int:id>')
@login_required
def delete_hof_entry(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    entry = HallOfFame.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    flash("Запись удалена.")
    return redirect(url_for('hall_of_fame'))


# --- ДОПОЛНИТЕЛЬНЫХ РАЗДЕЛЫ ---

@app.route('/main-league')
def main_league():
    return render_template('main_league_info.html')


@app.route('/biography')
def biography():
    return render_template('biography.html')


@app.route('/teams')
def teams_matrix():
    return render_template('teams_matrix.html')


@app.route('/practice')
def practice_hub():
    return render_template('practice.html')


# --- ИНФОРМАЦИОННЫЕ СТРАНИЦЫ О КЛУБЕ ---

@app.route('/about/faq')
def about_faq():
    return render_template('about_faq.html')


@app.route('/about/mission')
def about_mission():
    return render_template('about_mission.html')


@app.route('/about/organizers')
def about_organizers():
    return render_template('about_organizers.html')


@app.route('/about/partners')
def about_partners():
    return render_template('about_partners.html')


# --- АВТОРИЗАЦИЯ И УПРАВЛЕНИЕ ПРОФИЛЯМИ ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        picture_file = 'default.png'
        if form.avatar.data:
            picture_file = save_picture(form.avatar.data)

        selected_univ_name = request.form.get('university')
        assigned_university_id = None

        if selected_univ_name and selected_univ_name != 'Other':
            univ_record = University.query.filter_by(name=selected_univ_name).first()
            if univ_record:
                assigned_university_id = univ_record.id
            else:
                univ_record = University.query.filter(University.name.like(f"%{selected_univ_name}%")).first()
                if univ_record:
                    assigned_university_id = univ_record.id

        user = User(
            name=form.name.data,
            login=form.login.data,
            avatar=picture_file,
            password=hashed_password,
            university_id=assigned_university_id
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash("Account created! You can now login.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "danger")
            return redirect(request.url)

    all_unis = University.query.all()
    real_quota_data = {}
    for u in all_unis:
        real_quota_data[u.name] = {
            'label': u.name,
            'optId': f"opt-uni-{u.id}"
        }

    return render_template("register.html", form=form, real_quotas=real_quota_data)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(login=form.login.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash("You logged in successfully", "success")
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash("Incorrect login or password", "danger")
    return render_template("login.html", form=form)


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    return redirect('/login')


@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    user_participations = db.session.query(Participation).join(Tournament).filter(
        Participation.user_id == user.id
    ).all()

    confirmed_friends = user.get_confirmed_friends()
    incoming_requests = user.get_pending_requests() if current_user.is_authenticated and current_user.id == user.id else []

    rel_status = None
    is_sender = False
    if current_user.is_authenticated and current_user.id != user.id:
        rel_status = current_user.friendship_status_with(user.id)
        row = db.session.query(friendship).filter_by(user_id=current_user.id, friend_id=user.id).first()
        if row:
            is_sender = True

    return render_template(
        "profile.html",
        user=user,
        participations=user_participations,
        friends=confirmed_friends,
        incoming_requests=incoming_requests,
        rel_status=rel_status,
        is_sender=is_sender,
        quiz_topics=QUIZ_TOPICS
    )


@app.route('/profile')
@login_required
def my_profile():
    return redirect(url_for('profile', user_id=current_user.id))


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        if 'avatar' in request.files and request.files['avatar'].filename != '':
            current_user.avatar = save_picture(request.files['avatar'])

        db.session.commit()
        flash("Profile updated!")
        return redirect(url_for('my_profile'))
    return render_template("edit_profile.html", user=current_user)


@app.route('/profile/update_topic', methods=['POST'])
@login_required
def update_topic():
    new_topic = request.form.get('topic', '').strip()
    if new_topic in QUIZ_TOPICS or new_topic == 'Не указан':
        current_user.favorite_topic = new_topic
        db.session.commit()
        return {"status": "success", "topic": new_topic}
    return {"status": "error", "message": "Некорректная категория"}, 400


# --- СИСТЕМА ДВУХЭТАПНОЙ ДРУЖБЫ И СВЯЗЕЙ ЛИГИ ---

@app.route('/players', methods=['GET'])
@login_required
def players_hub():
    query = request.args.get('search', '').strip()
    if query:
        results = User.query.filter(User.name.like(f"%{query}%"), User.id != current_user.id).all()
    else:
        results = []
    return render_template("players_search.html", results=results, search_query=query)


@app.route('/friend/request/<int:friend_id>', methods=['POST'])
@login_required
def send_friend_request(friend_id):
    if current_user.id == friend_id:
        return redirect(url_for('profile', user_id=friend_id))

    existing = db.session.query(friendship).filter(
        ((friendship.c.user_id == current_user.id) & (friendship.c.friend_id == friend_id)) |
        ((friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id))
    ).first()

    if not existing:
        ins = friendship.insert().values(user_id=current_user.id, friend_id=friend_id, status='pending')
        db.session.execute(ins)
        db.session.commit()
        flash("Запрос в друзья успешно отправлен! Ожидайте подтверждения.", "success")
    else:
        flash("Запрос уже отправлен или вы уже друзья.", "info")

    return redirect(url_for('profile', user_id=friend_id))


@app.route('/friend/accept/<int:friend_id>', methods=['POST'])
@login_required
def accept_friend_request(friend_id):
    upd = friendship.update().where(
        (friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id)
    ).values(status='accepted')

    db.session.execute(upd)
    db.session.commit()
    flash("Заявка принята! Теперь вы официальные союзники ростера.", "success")
    return redirect(url_for('profile', user_id=current_user.id))


@app.route('/friend/decline/<int:friend_id>', methods=['POST'])
@login_required
def decline_friend_request(friend_id):
    dele = friendship.delete().where(
        ((friendship.c.user_id == current_user.id) & (friendship.c.friend_id == friend_id)) |
        ((friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id))
    )
    db.session.execute(dele)
    db.session.commit()
    flash("Связь аннулирована.", "warning")
    return redirect(url_for('profile', user_id=current_user.id))


# --- ЛИДЕРБОРД И УНИВЕРСИТЕТЫ ---

@app.route('/leaderboard')
def leaderboard():
    current_top = db.session.query(
        User, func.coalesce(func.sum(Participation.score), 0).label('total_score')
    ).outerjoin(Participation).group_by(User.id).order_by(func.sum(Participation.score).desc(), User.name.asc()).all()

    current_positions = {user.id: index + 1 for index, (user, _) in enumerate(current_top)}
    last_tournament = Tournament.query.filter_by(past=True).order_by(Tournament.date.desc()).first()

    previous_positions = {}
    if last_tournament:
        prev_top = db.session.query(User) \
            .outerjoin(Participation) \
            .filter((Participation.tournament_id != last_tournament.id) | (Participation.tournament_id.is_(None))) \
            .group_by(User.id).order_by(func.sum(Participation.score).desc(), User.name.asc()).all()

        previous_positions = {user.id: index + 1 for index, user in enumerate(prev_top)}

    top_participants = []
    for user, total_score in current_top[:20]:
        curr_pos = current_positions[user.id]

        if not last_tournament:
            trend = 'steady'
            trend_value = 0
        else:
            prev_pos = previous_positions.get(user.id)
            if prev_pos is None:
                trend = 'new'
                trend_value = 0
            else:
                trend_value = prev_pos - curr_pos
                if trend_value > 0:
                    trend = 'up'
                elif trend_value < 0:
                    trend = 'down'
                else:
                    trend = 'steady'

        top_participants.append({
            'user': user,
            'total_score': total_score,
            'trend': trend,
            'trend_value': abs(trend_value)
        })

    search_query = request.args.get('search', '').strip()
    search_results = []

    if search_query:
        search_results = User.query.filter(User.name.like(f"%{search_query}%")).all()

    return render_template(
        "leaderboard.html",
        top_participants=top_participants,
        search_results=search_results,
        search_query=search_query
    )


@app.route('/universities')
def universities():
    all_universities = University.query.all()
    leaderboard_data = []

    for univ in all_universities:
        users_in_univ = User.query.filter_by(university_id=univ.id).all()
        user_ids = [u.id for u in users_in_univ]

        total_score = 0
        if user_ids:
            participations = Participation.query.filter(
                Participation.user_id.in_(user_ids),
                Participation.score.isnot(None)
            ).all()
            total_score = sum(p.score for p in participations)

        leaderboard_data.append({
            'object': univ,
            'total_score': total_score
        })

    leaderboard_data.sort(key=lambda x: x['total_score'], reverse=True)
    return render_template('universities.html', universities=leaderboard_data)


@app.route('/universities/<int:id>')
def university_detail(id):
    univ = University.query.get_or_404(id)
    students = User.query.filter_by(university_id=univ.id).order_by(User.name.asc()).all()

    total_score = 0
    user_ids = [u.id for u in students]
    if user_ids:
        participations = Participation.query.filter(
            Participation.user_id.in_(user_ids),
            Participation.score.isnot(None)
        ).all()
        total_score = sum(p.score for p in participations)

    return render_template("university_details.html", university=univ, students=students, total_score=total_score)


# --- ОРГАНИЗАТОРСКОЕ УПРАВЛЕНИЕ ВУЗАМИ ---

@app.route('/admin/university/add', methods=['GET', 'POST'])
@login_required
def admin_add_university():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    if request.method == 'POST':
        name = request.form.get('name')
        city = request.form.get('city')
        description = request.form.get('description')
        website = request.form.get('website')
        is_host = True if request.form.get('is_host') else False
        is_sponsor = True if request.form.get('is_sponsor') else False

        if not name:
            flash('Название университета обязательно!', 'danger')
            return redirect(url_for('admin_add_university'))

        try:
            new_uni = University(
                name=name,
                city=city,
                description=description,
                website=website,
                is_host=is_host,
                is_sponsor=is_sponsor
            )
            db.session.add(new_uni)
            db.session.commit()
            flash(f'Университет "{name}" успешно добавлен!', 'success')
            return redirect(url_for('universities'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
            return redirect(url_for('admin_add_university'))

    return render_template('admin_add_university.html', university=None)


@app.route('/admin/university/<int:id>/quick-edit', methods=['GET', 'POST'])
@login_required
def admin_quick_edit_university(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    univ = University.query.get_or_404(id)

    if request.method == 'POST':
        univ.name = request.form.get('name')
        univ.city = request.form.get('city')
        univ.short_description = request.form.get('short_description')
        univ.is_host = True if request.form.get('is_host') else False
        univ.is_sponsor = True if request.form.get('is_sponsor') else False

        try:
            db.session.commit()
            flash(f'Карточка университета "{univ.name}" успешно обновлена!', 'success')
            return redirect(url_for('universities'))
        except Exception as e:
            db.session.rollback()
            return f"Ошибка быстрого редактирования: {e}"

    return render_template('admin_quick_edit_university.html', university=univ)


@app.route('/admin/university/<int:id>/edit-profile', methods=['GET', 'POST'])
@login_required
def admin_edit_university_profile(id):
    if current_user.status not in ['head', 'admin']:
        abort(403)

    univ = University.query.get_or_404(id)

    if request.method == 'POST':
        univ.description = request.form.get('description')
        univ.website = request.form.get('website')
        univ.address = request.form.get('address')
        univ.email = request.form.get('email')

        if 'logo' in request.files:
            file = request.files['logo']
            if file.filename != '':
                univ.logo = save_picture(file)

        try:
            db.session.commit()
            flash(f'Внутренний профиль университета успешно обновлен!', 'success')
            return redirect(url_for('university_detail', id=univ.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка обновления профиля: {e}', 'danger')
            return redirect(request.url)

    return render_template('admin_add_university.html', university=univ)


# ==========================================================================
# 5. ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БАЗЫ ДАННЫХ
# ==========================================================================

def init_database():
    try:
        db.create_all()

        if University.query.count() == 0:
            print("🌱 Заполнение базовых данных университетов...")

            auca = University(
                name="AUCA", city="Bishkek",
                short_description="Американский Университет в Центральной Азии — альма-матер лиги.",
                description="Американский Университет в Центральной Азии — официальный спонсор и альма-матер лиги ProQuiz.kg.",
                website="https://auca.kg",
                logo="https://ui-avatars.com/api/?name=AUCA&background=f59e0b&color=fff&size=256&font-size=0.4",
                is_host=True, is_sponsor=True
            )

            alatoo = University(
                name="Ala-Too", city="Bishkek",
                short_description="Международный университет Ала-Тоо.",
                description="Международный университет Ала-Тоо (AIU) — один из ведущих вузов Кыргызстана.",
                website="https://alatoo.edu.kg",
                logo="https://ui-avatars.com/api/?name=AIU&background=1e40af&color=ef4444&size=256&font-size=0.4",
                is_host=False, is_sponsor=False
            )

            manas = University(
                name="Manas", city="Bishkek",
                short_description="Кыргызско-Турецкий университет 'Манас'.",
                description="Кыргызско-Турецкий университет 'Манас' — престижный международный вуз.",
                website="https://manas.edu.kg",
                logo="https://ui-avatars.com/api/?name=MANAS&background=b91c1c&color=fff&size=256&font-size=0.4",
                is_host=False, is_sponsor=False
            )

            krsu = University(
                name="KRSU", city="Bishkek",
                short_description="Кыргызско-Российский Славянский Университет.",
                description="Кыргызско-Российский Славянский Университет имени Б.Н. Ельцина.",
                website="https://krsu.edu.kg",
                logo="https://ui-avatars.com/api/?name=КРСУ&background=e11d48&color=fff&size=256&font-size=0.4",
                is_host=False, is_sponsor=False
            )

            osce = University(
                name="OSCE Academy", city="Bishkek",
                short_description="Академия ОБСЕ в Бишкеке.",
                description="Академия ОБСЕ в Бишкеке — международный центр бакалавриата и магистратуры.",
                website="https://osce-academy.net",
                logo="https://ui-avatars.com/api/?name=OSCE&background=da291c&color=fff&size=256&font-size=0.4",
                is_host=False, is_sponsor=False
            )

            knu = University(
                name="KNU", city="Bishkek",
                short_description="Кыргызский Национальный Университет им. Ж.Баласагына."
            )
            bsu = University(
                name="BSU", city="Bishkek",
                short_description="Бишкекский Государственный Университет им. К.Карасаева."
            )
            salymbekov = University(
                name="Salymbekov University", city="Bishkek",
                short_description="Инновационный университет предпринимательства."
            )

            db.session.add_all([auca, alatoo, manas, krsu, osce, knu, bsu, salymbekov])

            if User.query.filter_by(status='head').count() == 0:
                head_user = User(
                    name="Nurmukhamed Abdumomun uulu",
                    login="Nur",
                    status="head",
                    avatar="Nur.jpg",
                    password=generate_password_hash("твой_супер_пароль")
                )

                moderator_user = User(
                    name="NURadmin",
                    login="admin",
                    status="admin",
                    avatar="default.png",
                    password=generate_password_hash("mod123")
                )

                db.session.add(head_user)
                db.session.add(moderator_user)

            db.session.commit()
            print("🚀 Новые университеты и роли организаторов успешно инициализированы!")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")


if __name__ == '__main__':
    with app.app_context():
        init_database()

    app.run(debug=True, host='0.0.0.0', port=5000)