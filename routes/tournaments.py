import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, flash, abort, redirect, jsonify, url_for
from flask_login import login_required, current_user
from extensions import db
from models import Tournament, Participation

# Initialize blueprint for league tournaments
tournaments_bp = Blueprint('tournaments', __name__)

# ==========================================================================
# 1. DYNAMIC CARD UPDATES AND STAGE HUBS
# ==========================================================================

@tournaments_bp.route('/admin/tournament/<int:id>/update_ongoing', methods=['POST'])
def update_tournament_ongoing(id):
    if not current_user.is_authenticated or current_user.status not in ['admin', 'head']:
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    tournament = Tournament.query.get(id)

    if tournament:
        try:
            tournament.title = data.get('title')
            tournament.date_str = data.get('date')
            tournament.league_type = data.get('tag')

            tournament.team_format = data.get('format', tournament.team_format)
            tournament.prize_pool = data.get('prize', tournament.prize_pool)

            if data.get('bg'):
                tournament.bg_image = data.get('bg')

            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Tournament successfully updated in DB'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': f'Database Error: {str(e)}'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Tournament not found in database'}), 404


@tournaments_bp.route('/tournaments')
def tournaments():
    current_season = "SEASON_01: INCEPTION"
    all_tournaments = Tournament.query.all()
    return render_template('tournaments.html', season=current_season, tournaments=all_tournaments)


@tournaments_bp.route('/tournaments/university-league/stages')
def tournament_stages_hub():
    current_season = "SEASON_01: INCEPTION"

    main_stages_presets = {
        1: {
            "name": "PLAYOFF STAGE",
            "teams_count": 16,
            "date": "October 2026",
            "status": "ongoing",
            "league_type": "qualification",
            "desc": "The first massive battle of the Main League season. 16 teams fight for the right to make it into the top 8. Mistakes here are costly."
        },
        2: {
            "name": "PRE-FINAL SHOWDOWN",
            "teams_count": 8,
            "date": "November 2026",
            "status": "upcoming",
            "league_type": "promotion",
            "desc": "The equator of the season. The tension doubles. Only the 8 strongest rosters meet in a face-to-face confrontation to reach the finals."
        },
        3: {
            "name": "THE GRAND FINAL",
            "teams_count": 4,
            "date": "December 2026",
            "status": "upcoming",
            "league_type": "promotion",
            "desc": "The culmination of the year. 4 absolute intellectual machines share the prize pool and the title of ProQuiz.ky champion."
        }
    }

    months_display = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
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
                "name": db_stage.title if db_stage.title else preset["name"],
                "teams_count": db_stage.teams_count if db_stage.teams_count else preset["teams_count"],
                "date": display_date,
                "status": db_stage.status if db_stage.status else preset["status"],
                "league_type": db_stage.league_type if db_stage.league_type else preset["league_type"],
                "is_main_league": True,
                "desc": db_stage.text if db_stage.text else preset["desc"]
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

    return render_template('stages_hub.html', season=current_season, stages=main_tournaments)


# ==========================================================================
# 2. RESULTS ADMINISTRATION AND EDITING
# ==========================================================================

@tournaments_bp.route('/tournaments/<int:id>/set_results', methods=['GET', 'POST'])
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
                flash("Results saved! Top-8 teams have been advanced to Pre-Final.", "success")
            elif next_tournament_id == 3:
                flash("Results saved! Top-4 teams have been advanced to Grand Final.", "success")
            else:
                flash("Grand Final closed! The absolute season champion has been determined.", "success")

            return redirect(url_for('tournaments.tournament_results', id=tournament.id))
        except Exception as e:
            db.session.rollback()
            return f"Database Error: {e}"

    return render_template("admin_set_results.html", tournament=tournament, participants=participants)


@tournaments_bp.route('/tournaments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tournament(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    if id <= 3 and current_user.status != 'head':
        abort(403)

    tournament_item = Tournament.query.get(id)

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
            tournament_item.language = ",".join(selected_languages) if selected_languages else "en"

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
                return redirect(url_for('tournaments.tournament_detail', id=tournament_item.id))
            except Exception as e:
                db.session.rollback()
                return f"Database Error: {e}"

    return render_template("edit_tournament.html", tournament=tournament_item)

# ==========================================================================
# 3. TOURNAMENTS, ROSTERS AND RESULTS VIEWING
# ==========================================================================

@tournaments_bp.route('/tournaments/<int:id>')
def tournament_detail(id):
    tournament_item = Tournament.query.get_or_404(id)

    js_date = tournament_item.date.strftime('%Y-%m-%dT%H:%M:%S') if tournament_item.date else "2026-12-31T23:59:59"
    months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    if tournament_item.date:
        dt = tournament_item.date
        formatted_date_str = f"{dt.day} {months_en[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M')}"
    elif hasattr(tournament_item, 'date_str') and tournament_item.date_str:
        formatted_date_str = tournament_item.date_str
    else:
        formatted_date_str = "Date not set"

    return render_template('tournament_detail.html', tournament=tournament_item, js_target_date=js_date, formatted_date_str=formatted_date_str)


@tournaments_bp.route('/tournaments/<int:id>/delete', methods=['POST'])
@login_required
def delete_tournament(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    tournament = Tournament.query.get_or_404(id)
    try:
        db.session.delete(tournament)
        db.session.commit()
        flash("Tournament deleted!", "success")
        return redirect(url_for('tournaments.tournaments'))
    except Exception as e:
        db.session.rollback()
        return str(e)


@tournaments_bp.route('/tournaments/<int:id>/participants')
def tournament_participants(id):
    tournament_item = Tournament.query.get_or_404(id)
    all_participations = Participation.query.filter_by(tournament_id=id).all()

    grouped_teams = {}
    for p in all_participations:
        if p.team_name not in grouped_teams:
            grouped_teams[p.team_name] = {'name': p.team_name, 'players': []}
        grouped_teams[p.team_name]['players'].append(p)

    return render_template("tournament_participants.html", tournament=tournament_item, teams=grouped_teams.values())


@tournaments_bp.route('/tournaments/<int:tournament_id>/team/<string:team_name>', methods=['GET', 'POST'])
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
        if new_password and len(new_password) >= 3:
            for member in team_members:
                member.team_password = new_password
            db.session.commit()
            flash("Team PIN code successfully updated by captain!", "success")
        else:
            flash("PIN code must consist of at least 3 characters!", "danger")
        return redirect(request.url)

    return render_template(
        "team_profile.html", tournament=tournament_item, team_name=team_name,
        members=team_members, captain_id=captain_participation.user_id,
        is_captain=is_captain, current_pin=captain_participation.team_password
    )


@tournaments_bp.route('/tournaments/<int:id>/results')
def tournament_results(id):
    tournament_item = Tournament.query.get_or_404(id)
    participants = Participation.query.filter_by(tournament_id=id).order_by(Participation.score.desc()).all()
    return render_template("tournament_results.html", tournament=tournament_item, participants=participants)


# ==========================================================================
# 4. TEAM REGISTRATION AND LEAVING TOURNAMENTS
# ==========================================================================

@tournaments_bp.route('/tournaments/<int:id>/register', methods=['GET', 'POST'])
@login_required
def tournament_register(id):
    tournament_item = Tournament.query.get_or_404(id)

    if tournament_item.past:
        flash("Registration is closed for past tournaments.", "danger")
        return redirect(url_for('tournaments.tournament_detail', id=tournament_item.id))

    if not current_user.university_id or not current_user.uni_profile:
        flash("Error: You must specify your university in your profile to register for the tournament!", "danger")
        return redirect(url_for('auth.edit_profile'))

    existing_participation = Participation.query.filter_by(user_id=current_user.id, tournament_id=id).first()
    if existing_participation:
        return render_template("tournament_register.html", tournament=tournament_item, already_registered=True)

    user_uni_name = current_user.uni_profile.name
    max_teams_allowed = 3 if user_uni_name.upper() == 'AUCA' else (1 if user_uni_name == 'Salymbekov University' else 2)

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
            flash("Please select a team!", "danger")
            return redirect(request.url)

        team_members = Participation.query.filter_by(tournament_id=id, team_name=selected_team).all()
        current_count = len(team_members)

        if current_count >= 3:
            flash(f"Error! Team {selected_team} is already completely full (3/3).", "danger")
            return redirect(request.url)

        if current_count == 0:
            if not input_password or len(input_password) < 4:
                flash("You are the first in this team! Create a 4-digit PIN code to secure the roster.", "danger")
                return redirect(request.url)
            final_password = input_password
        else:
            required_password = team_members[0].team_password
            if required_password and input_password != required_password:
                flash("Incorrect team PIN code! This roster is reserved by a group of friends.", "danger")
                return redirect(request.url)
            final_password = required_password

        participant = Participation(
            user_id=current_user.id,
            tournament_id=tournament_item.id,
            team_name=selected_team,
            email=f"{current_user.login}@proquiz.ky",
            phone_number=phone,
            team_password=final_password
        )

        try:
            db.session.add(participant)
            db.session.commit()
            flash(f"You have successfully joined the roster of {selected_team}!", "success")
            return redirect(url_for('tournaments.tournament_detail', id=tournament_item.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "danger")
            return redirect(request.url)

    return render_template("tournament_register.html", tournament=tournament_item, user_uni=user_uni_name, available_teams=available_teams)


@tournaments_bp.route('/tournaments/<int:id>/leave', methods=['POST'])
@login_required
def tournament_leave(id):
    participation = Participation.query.filter_by(user_id=current_user.id, tournament_id=id).first()

    if not participation:
        flash("You are not registered for this tournament.", "danger")
        return redirect(url_for('auth.profile'))

    if participation.tournament.past:
        flash("You cannot leave a team of a past tournament!", "danger")
        return redirect(url_for('auth.profile'))

    try:
        db.session.delete(participation)
        db.session.commit()
        flash("You have successfully left the team. The slot is released for other participants.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error while leaving the team: {e}", "danger")

    return redirect(url_for('auth.profile'))


# ==========================================================================
# 5. ECOSYSTEM PARTNER MEDIA AND DATA MANAGEMENT
# ==========================================================================

@tournaments_bp.route('/upload-partner-logo', methods=['POST'])
def upload_partner_logo():
    if not current_user.is_authenticated or current_user.status not in ['admin', 'head']:
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    partner_id = request.form.get('partner_id')
    partner_email = request.form.get('partner_email')
    partner_site = request.form.get('partner_site')

    if not partner_id:
        return jsonify({"status": "error", "message": "Partner ID not provided"}), 400

    config_path = 'partners_config.json'

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                partners_data = json.load(f)
        except Exception:
            partners_data = {}
    else:
        partners_data = {}

    if partner_id not in partners_data:
        partners_data[partner_id] = {}

    if partner_email:
        partners_data[partner_id]['email'] = partner_email
    if partner_site:
        partners_data[partner_id]['site'] = partner_site

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(partners_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error saving text data: {str(e)}"}), 500

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1]
            if partner_id == "uulkan":
                filename = "uulkan_avatar" + ext
            else:
                filename = f"{partner_id}_logo" + ext

            upload_folder = os.path.join('static', 'images', 'partners')
            try:
                os.makedirs(upload_folder, exist_ok=True)
                full_path = os.path.join(upload_folder, filename)
                file.save(full_path)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Error saving file: {str(e)}"}), 500

    return jsonify({"status": "success", "message": "Data successfully updated"}), 200