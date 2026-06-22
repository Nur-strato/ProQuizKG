from datetime import datetime
from flask_login import UserMixin
from extensions import db  # Чистый объект db из extensions.py

# ==========================================================================
# 1. СВЯЗУЮЩИЕ ТАБЛИЦЫ
# ==========================================================================

friendship = db.Table('friendship',
                      db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                      db.Column('friend_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                      db.Column('status', db.String(20), default='pending')
                      )


# ==========================================================================
# 2. МОДЕЛИ ДАННЫХ ЛИГИ
# ==========================================================================

class PracticeQuestion(db.Model):
    """Модель вопросов для практики"""
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


class University(db.Model):
    """Модель профилей университетов-участников"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_description = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    # 🔥 ИСПРАВЛЕНО: Дефолтный город переведен на английский язык
    city = db.Column(db.String(50), default='Bishkek')
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
        """Возвращает друзей с учетом двусторонней связи"""
        forward = db.session.query(User).join(friendship, friendship.c.friend_id == User.id).filter(
            friendship.c.user_id == self.id,
            friendship.c.status == 'accepted'
        ).all()

        backward = db.session.query(User).join(friendship, friendship.c.user_id == User.id).filter(
            friendship.c.friend_id == self.id,
            friendship.c.status == 'accepted'
        ).all()

        return list(set(forward + backward))

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
    status = db.Column(db.String(20), default='upcoming')  # upcoming, ongoing, completed
    league_type = db.Column(db.String(20), default='additional')  # main, additional
    teams_count = db.Column(db.Integer, default=16)
    date_str = db.Column(db.String(50), nullable=True)
    language = db.Column(db.String(10), default='ru')
    bg_image = db.Column(db.String(255), nullable=True)

    # 🔥 ИСПРАВЛЕНО: Дефолтные настройки формата переведены обратно на английский язык
    team_format = db.Column(db.String(100), default='Team Format (3 students)')
    prize_pool = db.Column(db.String(50), default='75 000')

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


class PartnerConfig(db.Model):
    """Модель конфигурации партнеров"""
    id = db.Column(db.String(50), primary_key=True)
    email = db.Column(db.String(120), nullable=True)
    site = db.Column(db.String(200), nullable=True)


class PredictionBet(db.Model):
    __tablename__ = 'prediction_bets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_name = db.Column(db.String(100), nullable=False, default="podium")
    amount = db.Column(db.Integer, nullable=False, default=0)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    stage_id = db.Column(db.Integer, default=2, nullable=False)
    team_1 = db.Column(db.String(100), nullable=True)
    team_2 = db.Column(db.String(100), nullable=True)
    team_3 = db.Column(db.String(100), nullable=True)
    team_4 = db.Column(db.String(100), nullable=True)
    is_processed = db.Column(db.Boolean, default=False)
    is_correct = db.Column(db.Boolean, default=False)


# === КРАСИВЫЙ И БЕЗОПАСНЫЙ ПЕРЕХВАТЧИК ДЛЯ БАЗЫ ДАННЫХ ===
from sqlalchemy import event


@event.listens_for(PredictionBet, 'before_insert')
def receive_before_insert(mapper, connection, target):
    target.team_name = "podium"