import os
import secrets
import json
from datetime import datetime
from flask import Blueprint, render_template, url_for, request, flash, abort, redirect, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import func

from extensions import db
from models import User, University, Participation, Tournament, friendship, HallOfFame

# Initialize blueprint for auth and user operations
auth_bp = Blueprint('auth', __name__)

# List of league quiz topics for management via Selector
QUIZ_TOPICS = [
    "General Knowledge", "World History", "Geography & Countries",
    "Cinema", "Music & Pop Culture", "IT & Technology",
    "Sports & Esports", "Literature & Art", "Science & Nature",
    "Logic & Puzzles", "Memes & Trends"
]


# ==========================================================================
# 1. WTFORMS VALIDATION FORMS
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


# ==========================================================================
# 2. HELPER UTILITIES
# ==========================================================================

def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)

    os.makedirs(os.path.dirname(picture_path), exist_ok=True)
    form_picture.save(picture_path)
    return picture_fn


# ==========================================================================
# 3. HALL OF FAME ROUTES & INFO PAGES
# ==========================================================================

@auth_bp.route('/gallery')
def hall_of_fame():
    entries = HallOfFame.query.order_by(HallOfFame.id.desc()).all()
    return render_template("hall_of_fame.html", hof_entries=entries)


@auth_bp.route('/gallery/upload', methods=['POST'])
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
        flash("Entry added to the Hall of Fame!", "success")
    return redirect(url_for('auth.hall_of_fame'))


@auth_bp.route('/gallery/delete/<int:id>')
@login_required
def delete_hof_entry(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)
    entry = HallOfFame.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    flash("Entry successfully deleted.", "warning")
    return redirect(url_for('auth.hall_of_fame'))


@auth_bp.route('/main-league')
def main_league():
    return render_template('main_league_info.html')


@auth_bp.route('/biography')
def biography():
    return render_template('biography.html')


@auth_bp.route('/teams')
def teams_matrix():
    return render_template('teams_matrix.html')


@auth_bp.route('/practice')
def practice_hub():
    return render_template('practice.html')


@auth_bp.route('/about/faq')
def about_faq():
    return render_template('about_faq.html')


@auth_bp.route('/about/mission')
def about_mission():
    return render_template('about_mission.html')


@auth_bp.route('/about/organizers')
def about_organizers():
    return render_template('about_organizers.html')


@auth_bp.sidebar_processor if hasattr(auth_bp, 'sidebar_processor') else auth_bp.context_processor
def inject_inception_terminal_data():
    all_universities = University.query.all()

    # Hardcoded limits configuration matching teams_matrix allocation registry
    university_limits = {
        'auca': 3, 'alatoo': 3, 'manas': 2, 'krsu': 2,
        'osceacademy': 1, 'knu': 1, 'bsu': 1, 'salymbekovuniversity': 1
    }

    battle_map_status = {}

    for univ in all_universities:
        code = univ.name.lower().strip().replace('-', '').replace(' ', '')

        if code in university_limits:
            # 🔥 INTEGRATED LOGIC: Count unique teams strictly locked into Tournament Stage 1 (id=1)
            # This completely filters out cloned advanced team entries inside Stage 2 or 3.
            registered_teams_count = db.session.query(Participation.team_name) \
                .filter(
                Participation.tournament_id == 1,
                Participation.team_name.like(f"{univ.name} - Team %")
            ) \
                .distinct() \
                .count()

            if registered_teams_count >= university_limits[code]:
                battle_map_status[code] = 'full'
            else:
                battle_map_status[code] = 'available'

    try:
        participants = Participation.query.filter_by(tournament_id=1).all()
        unique_teams = list(set([p.team_name for p in participants if p.team_name]))
    except Exception:
        unique_teams = []

    team_a = unique_teams[0] if len(unique_teams) > 0 else "AUCA Team 1"
    team_b = unique_teams[1] if len(unique_teams) > 1 else "KRSU Gladiators"

    seed_prob = (len(team_a) * 3) % 25 + 45
    prediction = {
        'team_a': team_a,
        'team_b': team_b,
        'prob_a': seed_prob,
        'prob_b': 100 - seed_prob
    }

    return dict(battle_map=battle_map_status, terminal_predict=prediction)


@auth_bp.route('/about/partners')
def about_partners():
    config_path = 'partners_config.json'
    partners_config = {}

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                partners_config = json.load(f)
        except Exception:
            partners_config = {}

    return render_template('about_partners.html', saved_data=partners_config)


# ==========================================================================
# 4. AUTHORIZATION AND USER PROFILES
# ==========================================================================

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        picture_file = 'default.png'
        if form.avatar.data:
            picture_file = save_picture(form.avatar.data)

        selected_univ_name = request.form.get('university', '').strip()
        assigned_university_id = None

        if selected_univ_name and selected_univ_name != 'Other':
            univ_record = University.query.filter_by(name=selected_univ_name).first()
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
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "danger")
            return redirect(request.url)

    all_unis = University.query.all()
    real_quota_data = {u.name: {'label': u.name, 'optId': f"opt-uni-{u.id}"} for u in all_unis}
    return render_template("register.html", form=form, real_quotas=real_quota_data)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(login=form.login.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash("You logged in successfully.", "success")
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash("Incorrect login or password.", "danger")
    return render_template("login.html", form=form)


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    user_participations = db.session.query(Participation).join(Tournament).filter(
        Participation.user_id == user.id).all()
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


@auth_bp.route('/profile')
@login_required
def my_profile():
    return redirect(url_for('auth.profile', user_id=current_user.id))


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        if 'avatar' in request.files and request.files['avatar'].filename != '':
            current_user.avatar = save_picture(request.files['avatar'])
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('auth.my_profile'))
    return render_template("edit_profile.html", user=current_user)


@auth_bp.route('/profile/update_topic', methods=['POST'])
@login_required
def update_topic():
    new_topic = request.form.get('topic', '').strip()
    if new_topic in QUIZ_TOPICS or new_topic == 'Not specified':
        current_user.favorite_topic = new_topic
        db.session.commit()
        return {"status": "success", "topic": new_topic}
    return {"status": "error", "message": "Invalid category selection"}, 400


# ==========================================================================
# 5. FRIEND SYSTEM & PLAYER SEARCH
# ==========================================================================

@auth_bp.route('/players', methods=['GET'])
@login_required
def players_hub():
    query = request.args.get('search', '').strip()
    results = User.query.filter(User.name.like(f"%{query}%"), User.id != current_user.id).all() if query else []
    return render_template("players_search.html", results=results, search_query=query)


@auth_bp.route('/friend/request/<int:friend_id>', methods=['POST'])
@login_required
def send_friend_request(friend_id):
    if current_user.id == friend_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"status": "error", "message": "You cannot add yourself"})
        return redirect(url_for('auth.profile', user_id=friend_id))

    existing = db.session.query(friendship).filter(
        ((friendship.c.user_id == current_user.id) & (friendship.c.friend_id == friend_id)) |
        ((friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id))
    ).first()

    if not existing:
        db.session.execute(friendship.insert().values(user_id=current_user.id, friend_id=friend_id, status='pending'))
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"status": "success", "message": "Request sent successfully"})

        flash("Friend request sent successfully!", "success")
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"status": "error", "message": "Request already exists"})
        flash("Friend request already pending or connection exists.", "info")

    return redirect(url_for('auth.profile', user_id=friend_id))


@auth_bp.route('/friend/accept/<int:friend_id>', methods=['POST'])
@login_required
def accept_friend_request(friend_id):
    db.session.execute(friendship.update().where(
        (friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id)).values(status='accepted'))
    db.session.commit()
    flash("Friend request accepted!", "success")
    return redirect(url_for('auth.profile', user_id=current_user.id))


@auth_bp.route('/friend/decline/<int:friend_id>', methods=['POST'])
@login_required
def decline_friend_request(friend_id):
    db.session.execute(friendship.delete().where(
        ((friendship.c.user_id == current_user.id) & (friendship.c.friend_id == friend_id)) | (
                (friendship.c.user_id == friend_id) & (friendship.c.friend_id == current_user.id))))
    db.session.commit()
    flash("Connection removed.", "warning")
    return redirect(url_for('auth.profile', user_id=current_user.id))


# ==========================================================================
# 6. LEADERBOARDS AND UNIVERSITY STATISTICS
# ==========================================================================

@auth_bp.route('/leaderboard')
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
            'user': user, 'total_score': total_score, 'trend': trend, 'trend_value': abs(trend_value)
        })

    search_query = request.args.get('search', '').strip()
    search_results = User.query.filter(User.name.like(f"%{search_query}%")).all() if search_query else []

    return render_template("leaderboard.html", top_participants=top_participants, search_results=search_results,
                           search_query=search_query)


@auth_bp.route('/universities')
def universities():
    all_universities = University.query.all()
    leaderboard_data = []

    for univ in all_universities:
        users_in_univ = User.query.filter_by(university_id=univ.id).all()
        user_ids = [u.id for u in users_in_univ]

        total_score = 0
        if user_ids:
            participations = Participation.query.filter(Participation.user_id.in_(user_ids),
                                                        Participation.score.isnot(None)).all()
            total_score = sum(p.score for p in participations)

        leaderboard_data.append({'object': univ, 'total_score': total_score})

    leaderboard_data.sort(key=lambda x: x['total_score'], reverse=True)
    return render_template('universities.html', universities=leaderboard_data)


@auth_bp.route('/universities/<int:id>')
def university_detail(id):
    univ = University.query.get_or_404(id)
    students = User.query.filter_by(university_id=univ.id).order_by(User.name.asc()).all()

    total_score = 0
    user_ids = [u.id for u in students]
    if user_ids:
        participations = Participation.query.filter(Participation.user_id.in_(user_ids),
                                                    Participation.score.isnot(None)).all()
        total_score = sum(p.score for p in participations)

    return render_template("university_details.html", university=univ, students=students, total_score=total_score)


@auth_bp.route('/profile/search_users', methods=['GET'])
@login_required
def search_users_json():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    users = User.query.filter(User.name.like(f"%{query}%"), User.id != current_user.id).all()

    confirmed_friends_ids = [f.id for f in current_user.get_confirmed_friends()]
    sent_requests_rows = db.session.query(friendship).filter_by(user_id=current_user.id, status='pending').all()
    sent_requests_ids = [r.friend_id for r in sent_requests_rows]

    results = []
    for u in users:
        results.append({
            "id": u.id,
            "name": u.name,
            "avatar": u.avatar if u.avatar else "default.png",
            "is_friend": u.id in confirmed_friends_ids,
            "request_sent": u.id in sent_requests_ids
        })

    return jsonify(results)