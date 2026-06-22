from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from extensions import db
from models import Tournament, PredictionBet
from sqlalchemy import func

predict_bp = Blueprint('predict', __name__)

# 🔥 ИСПРАВЛЕНО: Пул вузов приведен к строгому английскому языку в соответствии с БД
TEAMS_POOL = [
    "AUCA", "Ala-Too", "Manas",
    "KRSU", "OSCE Academy",
    "KNU", "BSU", "Salymbekov University"
]


@predict_bp.route('/predict', methods=['GET'])
@login_required
def index():
    try:
        current_stage = int(request.args.get('stage', 2))
        if current_stage not in [1, 2, 3]:
            current_stage = 2
    except (ValueError, TypeError):
        current_stage = 2

    user_bet_stage = PredictionBet.query.filter_by(
        user_id=current_user.id,
        tournament_id=1,
        stage_id=current_stage
    ).first()

    # Считаем ВСЕ голоса комьюнити для этой стадии турнира
    total_bets = PredictionBet.query.filter_by(tournament_id=1, stage_id=current_stage).count()
    print(f"--- [DEBUG INDEX] Total predictions in DB for stage {current_stage}: {total_bets} ---")

    # Сбор полной динамической матрицы голосов (1, 2, 3, 4 места)
    matrix_stats = {team: {'p1': 0, 'p2': 0, 'p3': 0, 'p4': 0} for team in TEAMS_POOL}

    if total_bets > 0:
        # 1st places
        p1_counts = db.session.query(PredictionBet.team_1, func.count(PredictionBet.id)).filter_by(
            tournament_id=1, stage_id=current_stage
        ).group_by(PredictionBet.team_1).all()
        for team, count in p1_counts:
            if team in matrix_stats: matrix_stats[team]['p1'] = round((count / total_bets) * 100)

        # 2nd places
        p2_counts = db.session.query(PredictionBet.team_2, func.count(PredictionBet.id)).filter_by(
            tournament_id=1, stage_id=current_stage
        ).group_by(PredictionBet.team_2).all()
        for team, count in p2_counts:
            if team in matrix_stats: matrix_stats[team]['p2'] = round((count / total_bets) * 100)

        # 3rd places
        p3_counts = db.session.query(PredictionBet.team_3, func.count(PredictionBet.id)).filter_by(
            tournament_id=1, stage_id=current_stage
        ).group_by(PredictionBet.team_3).all()
        for team, count in p3_counts:
            if team in matrix_stats: matrix_stats[team]['p3'] = round((count / total_bets) * 100)

        # 4th places
        p4_counts = db.session.query(PredictionBet.team_4, func.count(PredictionBet.id)).filter_by(
            tournament_id=1, stage_id=current_stage
        ).group_by(PredictionBet.team_4).all()
        for team, count in p4_counts:
            if team in matrix_stats: matrix_stats[team]['p4'] = round((count / total_bets) * 100)

    user_history = PredictionBet.query.filter_by(user_id=current_user.id).order_by(PredictionBet.id.desc()).all()

    return render_template(
        'predict.html',
        teams=TEAMS_POOL,
        current_stage=current_stage,
        user_bet_stage2=user_bet_stage,
        matrix_stats=matrix_stats,
        history=user_history
    )


@predict_bp.route('/predict/place_bet', methods=['POST'])
@login_required
def place_bet():
    print("--- [DEBUG POST] place_bet route called! Starting processing... ---")
    try:
        tournament_id = int(request.form.get('tournament_id', 1))
        stage_id = int(request.form.get('stage_id', 2))
    except (ValueError, TypeError):
        flash("Critical error: invalid tournament or stage ID format.", "danger")
        return redirect(url_for('predict.index'))

    t1 = request.form.get('team_1')
    t2 = request.form.get('team_2')
    t3 = request.form.get('team_3')
    t4 = request.form.get('team_4')

    print(f"--- [DEBUG POST] Received universities: {t1}, {t2}, {t3}, {t4} ---")

    if not all([t1, t2, t3, t4]):
        flash("Error: Please fill in all 4 podium positions before saving!", "danger")
        return redirect(url_for('predict.index', stage=stage_id))

    if len({t1, t2, t3, t4}) != 4:
        flash("Error: A university cannot be duplicated on the podium.", "warning")
        return redirect(url_for('predict.index', stage=stage_id))

    now_time = datetime.now(timezone.utc).replace(tzinfo=None)

    existing_bet = PredictionBet.query.filter_by(
        user_id=current_user.id,
        tournament_id=tournament_id,
        stage_id=stage_id
    ).first()

    if existing_bet:
        print("--- [DEBUG POST] Old user prediction found. Checking 24h cooldown... ---")
        bet_time = existing_bet.date if hasattr(existing_bet, 'date') and existing_bet.date else current_user.date

        if bet_time and bet_time.tzinfo is not None:
            bet_time = bet_time.astimezone(timezone.utc).replace(tzinfo=None)

        if bet_time and (now_time - bet_time < timedelta(days=1)):
            time_passed = now_time - bet_time
            time_remaining = timedelta(days=1) - time_passed
            hours = int(time_remaining.total_seconds() // 3600)
            minutes = int((time_remaining.total_seconds() % 3600) // 60)

            print(f"--- [DEBUG POST] Rejected: Cooldown active. Remaining: {hours}h {minutes}m ---")
            flash(f"You can only change your prediction once a day! Try again in {hours}h {minutes}m.",
                  "warning")
            return redirect(url_for('predict.index', stage=stage_id))

        print("--- [DEBUG POST] Cooldown expired. Updating existing prediction in DB... ---")
        bet = existing_bet
    else:
        print("--- [DEBUG POST] Creating new prediction in DB... ---")
        bet = PredictionBet()
        bet.user_id = current_user.id
        bet.tournament_id = tournament_id
        bet.stage_id = stage_id
        bet.team_name = "podium"
        bet.is_processed = False

    bet.team_1 = t1
    bet.team_2 = t2
    bet.team_3 = t3
    bet.team_4 = t4
    bet.date = now_time

    try:
        if not existing_bet:
            db.session.add(bet)
        db.session.commit()
        print("--- [DEBUG POST] SUCCESS! db.session.commit() successful! ---")
        flash(f"Your Top-4 for Stage 0{stage_id} successfully saved!", "success")
    except Exception as e:
        db.session.rollback()
        print(f"--- [DEBUG POST] CRITICAL DATABASE ERROR: {e} ---")
        flash("Internal database error occurred while saving.", "danger")

    return redirect(url_for('predict.index', stage=stage_id))


@predict_bp.route('/predict/admin/settle/<int:tournament_id>', methods=['POST'])
@login_required
def settle_match(tournament_id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    try:
        stage_id = int(request.form.get('stage_id', 2))
    except (ValueError, TypeError):
        stage_id = 2

    win_1 = request.form.get('win_1')
    win_2 = request.form.get('win_2')
    win_3 = request.form.get('win_3')
    win_4 = request.form.get('win_4')

    bets = PredictionBet.query.filter_by(tournament_id=tournament_id, stage_id=stage_id, is_processed=False).all()

    for bet in bets:
        bet.is_processed = True
        if bet.team_1 == win_1 and bet.team_2 == win_2 and bet.team_3 == win_3 and bet.team_4 == win_4:
            bet.is_correct = True
        else:
            bet.is_correct = False

    db.session.commit()
    flash(f"Success! All predictions for Stage {stage_id} have been settled.", "success")
    return redirect(url_for('predict.index', stage=stage_id))