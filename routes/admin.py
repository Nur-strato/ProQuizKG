import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, flash, abort, redirect, jsonify, url_for
from flask_login import login_required, current_user
from sqlalchemy.sql import func
from extensions import db
from models import PracticeQuestion, Tournament, University
from routes.auth import save_picture  # Import picture utility from auth blueprint

# Initialize league administration blueprint
admin_bp = Blueprint('admin', __name__)

# ==========================================================================
# 1. PRACTICE SYSTEM & QUESTION ARENA (API & MANAGEMENT)
# ==========================================================================

@admin_bp.route('/api/practice/questions/<theme_key>')
def get_practice_questions(theme_key):
    valid_themes = ['logic', 'history', 'science', 'geography', 'culture', 'literature']
    if theme_key not in valid_themes:
        return jsonify({'error': 'Invalid question category selection'}), 400

    questions = PracticeQuestion.query.filter_by(theme=theme_key, is_active=True) \
        .order_by(func.random()) \
        .limit(10) \
        .all()

    if not questions:
        return jsonify([])

    return jsonify([q.to_dict() for q in questions])


@admin_bp.route('/admin/practice/add', methods=['GET', 'POST'])
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
            flash("Error: Please fill in all required form fields!", "danger")
            return redirect(url_for('admin.admin_add_practice_question'))

        try:
            new_q = PracticeQuestion(
                theme=theme,
                question_text=question_text,
                answer=answer,
                explanation=explanation if explanation else None
            )
            db.session.add(new_q)
            db.session.commit()
            flash("🎉 Question successfully saved to the Arena database!", "success")
            return redirect(url_for('admin.admin_add_practice_question'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving entry: {e}", "danger")
            return redirect(url_for('admin.admin_add_practice_question'))

    stats = {}
    themes_list = ['logic', 'history', 'science', 'geography', 'culture', 'literature']
    for t in themes_list:
        stats[t] = PracticeQuestion.query.filter_by(theme=t).count()

    total_count = PracticeQuestion.query.count()
    return render_template('admin_add_question.html', stats=stats, total_count=total_count)


@admin_bp.route('/admin/practice/questions')
@login_required
def admin_view_practice_questions():
    if current_user.status not in ['admin', 'head']:
        abort(403)

    local_db = {
        'logic': [
            {'question_text': "In detective novels, IT is frequently used to wipe fingerprints and hide traces...", 'answer': "Paper napkins / cellulose cotton", 'explanation': "Napkins smoothly wipe away grease prints without leaving specific fibers.", 'is_local': True},
            {'question_text': "If A = 5, B = 10, and their sum multiplied by two equals 30...", 'answer': "25", 'explanation': "(10 - 5) squared equals 5 * 5 = 25.", 'is_local': True},
            {'question_text': "What technical and medical term combines a pipeline element and an anatomical structure?", 'answer': "Valve", 'explanation': "Mechanical valves direct fluid flows just like biological heart valves.", 'is_local': True},
            {'question_text': "What logical concept links a chess knight jumping and a sudden evolutionary breakthrough?", 'answer': "Leap", 'explanation': "The knight performs a leap over elements, symbolizing non-linear progression.", 'is_local': True},
            {'question_text': "Continue the classic astronomical sequence of planets: Mercury, Venus, Earth...", 'answer': "Mars", 'explanation': "Classic chronological ordering of solar system planets away from the Sun.", 'is_local': True},
            {'question_text': "What architectural invention allowed early humans to look outside without letting weather elements in?", 'answer': "Window", 'explanation': "Windows function as transparent barriers separating interiors from the external horizon.", 'is_local': True},
            {'question_text': "According to folklore riddles, what flies across valleys without having wings?", 'answer': "Cloud", 'explanation': "Atmospheric cloud mass movement simulates majestic wingless flying.", 'is_local': True},
            {'question_text': "It is always located directly ahead of us, structuring all our current goals and anxieties...", 'answer': "Future", 'explanation': "Philosophical concept defining the chronological state yet to occur.", 'is_local': True},
            {'question_text': "The more physical volume you extract out of it, the larger its structure grows...", 'answer': "Hole", 'explanation': "Removing soil directly increases the dimensions of a hole.", 'is_local': True},
            {'question_text': "Name the lightest and most abundantly common chemical element in the observable universe...", 'answer': "Hydrogen", 'explanation': "Hydrogen (H) possesses atomic mass 1 and forms the basis of star structures.", 'is_local': True}
        ],
        'history': [
            {'question_text': "In what historical year did the famous Battle of Waterloo take place...", 'answer': "1815", 'explanation': "The heavy combat concluded on June 18, 1815, sealing Napoleon's fate.", 'is_local': True},
            {'question_text': "Which ancient civilization developed hieroglyphic script and monumental pyramids along the Nile...", 'answer': "Ancient Egypt", 'explanation': "Egyptians carved distinct symbols and built stone tombs for dynastic pharaohs.", 'is_local': True},
            {'question_text': "Who is officially recorded as the first formal Emperor of the integrated Roman Empire...", 'answer': "Augustus", 'explanation': "Born Octavian, the grandnephew of Julius Caesar reorganized the state into an empire.", 'is_local': True},
            {'question_text': "Which Ancient Greek city-state is universally recognized as the cradle of democratic direct voting systems...", 'answer': "Athens", 'explanation': "Athenian ecclesia enabled voting procedures for all recognized free citizens.", 'is_local': True},
            {'question_text': "Which massive battle of WWII is widely considered the ultimate strategic turning point on the Eastern Front...", 'answer': "Battle of Stalingrad", 'explanation': "The encirclement and destruction of the Wehrmacht 6th Army broke German momentum.", 'is_local': True},
            {'question_text': "Who commanded the Spanish fleet expedition that accidentally arrived in the Americas in 1492...", 'answer': "Christopher Columbus", 'explanation': "The navigator sought an alternate western passage to the wealthy trade markets of India.", 'is_local': True},
            {'question_text': "In which island nation of Europe did the first Industrial Revolution officially originate...", 'answer': "Great Britain", 'explanation': "Steam engine integration revolutionized production mills and factories first in Britain.", 'is_local': True},
            {'question_text': "What was the name of the Soviet cosmonaut who completed the first manned orbital space flight in history...", 'answer': "Yuri Gagarin", 'explanation': "On April 12, 1961, the historic Vostok-1 capsule safely orbited Earth.", 'is_local': True},
            {'question_text': "Which royal dynasty continuously ruled the Russian Empire for over 300 years until 1917...", 'answer': "Romanov", 'explanation': "The dynastic timeline started with Michael Romanov's coronation in 1613.", 'is_local': True},
            {'question_text': "The assassination of which political figure in Sarajevo triggered the immediate outbreak of World War I...", 'answer': "Archduke Franz Ferdinand", 'explanation': "The Austrian heir to the throne was targeted by a Serbian nationalist group.", 'is_local': True}
        ],
        'science': [
            {'question_text': "Which solar system planet is colloquially referred to in astronomy as the 'Red Planet'...", 'answer': "Mars", 'explanation': "Iron oxide dust covering Martian regolith reflects a distinct reddish hue.", 'is_local': True},
            {'question_text': "What fundamental physical force maintains cosmic bodies in structured stellar orbits...", 'answer': "Gravity", 'explanation': "Newtonian and Einsteinian physics define gravity as space-time attraction.", 'is_local': True},
            {'question_text': "What is the biochemical name of the process converting light energy into stable organic chemical bounds...", 'answer': "Photosynthesis", 'explanation': "Occurs inside specialized plant chloroplast structures utilizing carbon dioxide and water.", 'is_local': True},
            {'question_text': "Which carbon allotrope is recognized as the hardest naturally occurring mineral on Earth...", 'answer': "Diamond", 'explanation': "Features a crystalline cubic lattice structure scoring a perfect 10 on the Mohs scale.", 'is_local': True},
            {'question_text': "What thermal value on the Celsius scale corresponds to the theoretical baseline of Absolute Zero...", 'answer': "−273.15 °C", 'explanation': "The exact thermodynamic baseline where internal molecular kinetic motion ceases entirely.", 'is_local': True},
            {'question_text': "Which double-helix macromolecule encodes genetic blueprints across biological generations...", 'answer': "DNA", 'explanation': "Deoxyribonucleic acid stores sequences via four distinct nucleotide bases.", 'is_local': True},
            {'question_text': "Which gaseous element dominates Earth's atmospheric composition by absolute volume?", 'answer': "Nitrogen", 'explanation': "Stable nitrogen molecules (N2) account for roughly 78% of dry atmospheric air.", 'is_local': True},
            {'question_text': "Which theoretical physicist developed the Special and General Theories of Relativity...", 'answer': "Albert Einstein", 'explanation': "Einstein fundamentally altered human perception of gravity, space, and relative time vectors.", 'is_local': True},
            {'question_text': "What is the standard scientific term for the smallest chemically indivisible, electrically neutral unit of matter...", 'answer': "Atom", 'explanation': "Atoms pack a dense positive nucleus wrapped in a probability cloud of electrons.", 'is_local': True},
            {'question_text': "Which transition metal possesses the rare physical property of staying fluid at standard room temperature...", 'answer': "Mercury", 'explanation': "Mercury (Hg) transitions into a solid structure only below −39 °C.", 'is_local': True}
        ],
        'geography': [
            {'question_text': "Which ocean basin is recorded as the deepest and largest by total surface surface area on Earth...", 'answer': "Pacific Ocean", 'explanation': "Its scope comfortably exceeds the combined area of all planetary dry land masses.", 'is_local': True},
            {'question_text': "Which sovereign modern nation handles the largest absolute geographic territory in the world...", 'answer': "Russia", 'explanation': "Spans across Eastern Europe and Northern Asia, covering over 17.1 million square kilometers.", 'is_local': True},
            {'question_text': "In which major mountain system of Asia is the highest peak of the world, Mount Everest, situated...", 'answer': "Himalayas", 'explanation': "The massive Himalayan fault zone straddles the territory of China and Nepal.", 'is_local': True},
            {'question_text': "Which South American water current system is recognized as the longest and most voluminous river array...", 'answer': "Amazon", 'explanation': "Feeds the largest structural drainage basin, out-pouring massive volumes into the Atlantic.", 'is_local': True},
            {'question_text': "Name the capital city of Japan that forms the single most populated urban metropolitan area on Earth.", 'answer': "Tokyo", 'explanation': "The main financial node of the Japanese archipelago hosting over 37 million residents.", 'is_local': True},
            {'question_text': "Which permanently inhabited continental landmass stands as the driest, lowest, and flattest geographic array?", 'answer': "Australia", 'explanation': "Arid desert ecosystems and low-lying plateaus cover the vast majority of its interior.", 'is_local': True},
            {'question_text': "Which landlocked hypersaline water body in the Middle East prevents complex aquatic life...", 'answer': "Dead Sea", 'explanation': "Mineral concentrations hover near 300–310 parts per thousand, enhancing buoyancy.", 'is_local': True},
            {'question_text': "Through which European capital metropolitan area is the Prime Meridian line scientifically anchored?", 'answer': "London", 'explanation': "The Royal Greenwich Observatory sits in a historic south-eastern sector of London.", 'is_local': True},
            {'question_text': "Which massive African landscape forms the single largest hot desert zone on the globe?", 'answer': "Sahara", 'explanation': "Covers over 9 million square kilometers across the entire top tier of the African continent.", 'is_local': True},
            {'question_text': "Which single federal nation-state completely occupies an entire distinct continent by itself?", 'answer': "Australia", 'explanation': "The Commonwealth of Australia manages the entire main landmass plus surrounding islands.", 'is_local': True}
        ],
        'culture': [
            {'question_text': "Which British filmmaker directed complex cinematic blockbusters like 'Inception' and 'Interstellar'...", 'answer': "Christopher Nolan", 'explanation': "Famous for nonlinear timelines, complex editing architectures, and practical effects usage.", 'is_local': True},
            {'question_text': "Which legendary rock band recorded the iconic multi-genre piece 'Bohemian Rhapsody' in 1975?", 'answer': "Queen", 'explanation': "Freddie Mercury combined operatic structures, hard rock riffs, and choral arrangements.", 'is_local': True},
            {'question_text': "Which Renaissance painting by Leonardo da Vinci, secured behind bulletproof glass in the Louvre, is world-famous?", 'answer': "Mona Lisa", 'explanation': "The enigmatic portrait of Lisa Gherardini showcases masterful sfumato blending.", 'is_local': True},
            {'question_text': "Who authored the high-fantasy epic literary trilogy 'The Lord of the Rings'?", 'answer': "J.R.R. Tolkien", 'explanation': "The Oxford philologist meticulously engineered entire languages and Middle-earth mythologies.", 'is_local': True},
            {'question_text': "Which highly successful animation studio owned by Disney produced 'Toy Story' and 'WALL-E'?", 'answer': "Pixar", 'explanation': "The studio spearheaded a complete digital graphics revolution in CGI cinema history.", 'is_local': True},
            {'question_text': "Which American pop singer retains the status of highest-selling female artist, crowned the 'Queen of Pop'?", 'answer': "Madonna", 'explanation': "Recognized for continuous artistic reinvention and massive cultural impact across decades.", 'is_local': True},
            {'question_text': "Which Hollywood actor portrayed the eccentric, charismatic pirate captain Jack Sparrow?", 'answer': "Johnny Depp", 'explanation': "Depp's unique character performance turned the adventure franchise into a global empire.", 'is_local': True},
            {'question_text': "In which space opera franchise created by George Lucas are the Force, Jedi, and Sith central mechanics?", 'answer': "Star Wars", 'explanation': "An expansive cultural mythos that transformed global merchandising and movie-making standards.", 'is_local': True},
            {'question_text': "In which California city does the annual star-studded Academy Awards ('Oscars') ceremony take place?", 'answer': "Los Angeles", 'explanation': "The prestigious industry event unfolds at the famous Dolby Theatre in Hollywood.", 'is_local': True},
            {'question_text': "Which short-video platform sparked a global shift toward algorithmic vertical mobile feeds?", 'answer': "TikTok", 'explanation': "Engineered by ByteDance, the software redefined user content consumption patterns globally.", 'is_local': True}
        ],
        'literature': [
            {'question_text': "Who authored the first foundational realistic novel-in-verse of Russian literature, 'Eugene Onegin'?", 'answer': "Alexander Pushkin", 'explanation': "The literary masterpiece was developed by the poet across a span of more than seven years.", 'is_local': True},
            {'question_text': "Which iconic English playwright of the Renaissance era crafted the timeless tragedy 'Romeo and Juliet'?", 'answer': "William Shakespeare", 'explanation': "The definitive drama about feuding houses and doomed romance was staged around 1595.", 'is_local': True},
            {'question_text': "Who penned the historical four-volume literary masterpiece epic 'War and Peace'?", 'answer': "Leo Tolstoy", 'explanation': "Offers a profound psychological analysis of Russian society during the Napoleonic wars.", 'is_local': True},
            {'question_text': "Under what famous pen name did Samuel Clemens write the classic adventures of Tom Sawyer and Huck Finn?", 'answer': "Mark Twain", 'explanation': "The riverboat term indicates a safe depth measurement of two fathoms.", 'is_local': True},
            {'question_text': "Who authored the definitive dystopian political novel '1984', introducing terms like 'Big Brother'?", 'answer': "George Orwell", 'explanation': "The literature stands as a chilling systemic critique against total surveillance regimes.", 'is_local': True},
            {'question_text': "Which Florentine poet crafted the epic medieval allegorical journey through afterlife realms titled 'The Divine Comedy'?", 'answer': "Dante Alighieri", 'explanation': "His conceptual structure laid down the core linguistic layout of modern Italian.", 'is_local': True},
            {'question_text': "Which British physician-turned-writer introduced the brilliant consultant detective Sherlock Holmes?", 'answer': "Arthur Conan Doyle", 'explanation': "Doyle's narratives popularized systematic forensic observation and deductive reasoning.", 'is_local': True},
            {'question_text': "Which psychological novel by Fyodor Dostoevsky tracks Raskolnikov's split theory regarding exceptional people...", 'answer': "Crime and Punishment", 'explanation': "A deep exploration of moral breakdown, systemic guilt, and spiritual redemption.", 'is_local': True},
            {'question_text': "Which professional French aviator wrote the profound, touching philosophical fable 'The Little Prince'?", 'answer': "Antoine de Saint-Exupéry", 'explanation': "The poetic allegory critiques adult perspectives while championing empathy and responsibility.", 'is_local': True},
            {'question_text': "Which British author penned the globally successful fantasy universe centering on the Hogwarts School of Witchcraft?", 'answer': "J.K. Rowling", 'explanation': "The Harry Potter chronicles secured status as the best-selling book franchise in history.", 'is_local': True}
        ]
    }

    db_questions = PracticeQuestion.query.order_by(PracticeQuestion.created_at.asc()).all()
    grouped_questions = {t: [] for t in ['logic', 'history', 'science', 'geography', 'culture', 'literature']}

    for theme, q_list in local_db.items():
        grouped_questions[theme] = list(q_list)

    for q in db_questions:
        if q.theme in grouped_questions:
            grouped_questions[q.theme].append({
                'id': q.id,
                'question_text': q.question_text,
                'answer': q.answer,
                'explanation': q.explanation if q.explanation else "No analytical explanation specified.",
                'created_at': q.created_at,
                'is_local': False
            })

    counts = {theme: len(lst) for theme, lst in grouped_questions.items()}
    total_count = sum(counts.values())

    return render_template(
        'admin_view_questions.html',
        grouped=grouped_questions,
        counts=counts,
        total_count=total_count
    )


@admin_bp.route('/admin/practice/questions/<int:id>/edit', methods=['POST'])
@login_required
def admin_edit_practice_question(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)

    question = PracticeQuestion.query.get_or_404(id)
    question.question_text = request.form.get('question_text', '').strip()
    question.answer = request.form.get('answer', '').strip()
    question.explanation = request.form.get('explanation', '').strip()

    if not question.question_text or not question.answer:
        flash("Error: Question text and correct answer cannot be empty fields!", "danger")
        return redirect(url_for('admin.admin_view_practice_questions'))

    try:
        db.session.commit()
        flash("🎉 Question changes successfully synchronized in the Arena database!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving changes: {e}", "danger")

    return redirect(url_for('admin.admin_view_practice_questions'))


@admin_bp.route('/admin/practice/questions/<int:id>/delete', methods=['POST'])
@login_required
def admin_delete_practice_question(id):
    if current_user.status not in ['admin', 'head']:
        abort(403)
    question = PracticeQuestion.query.get_or_404(id)
    try:
        db.session.delete(question)
        db.session.commit()
        flash("Question successfully eliminated from the database.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error during deletion process: {e}", "danger")
    return redirect(url_for('admin.admin_view_practice_questions'))


# ==========================================================================
# 2. TOURNAMENT MANAGEMENT & GLOBAL ADMINISTRATIVE ACCESS RENDER
# ==========================================================================

@admin_bp.route('/admin/init-db')
@login_required
def admin_init_db():
    if current_user.status != 'admin':
        abort(403)
    try:
        db.create_all()
        flash("All database tables have been successfully created!", "success")
    except Exception as e:
        flash(f"Initialization Error: {e}", "danger")
        return str(e)
    return redirect(url_for('admin.admin'))


@admin_bp.route('/admin', methods=['POST', 'GET'])
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
        next_id = 4 if max_id is None or max_id < 3 else max_id + 1

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
        return redirect(url_for('tournaments.tournaments'))

    return render_template("admin.html")


# ==========================================================================
# 3. UNIVERSITY PROFILES CONTROL NODES
# ==========================================================================

@admin_bp.route('/admin/university/add', methods=['GET', 'POST'])
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
            flash('University title name is mandatory!', 'danger')
            return redirect(url_for('admin.admin_add_university'))

        try:
            new_uni = University(
                name=name, city=city, description=description,
                website=website, is_host=is_host, is_sponsor=is_sponsor
            )
            db.session.add(new_uni)
            db.session.commit()
            flash(f'University "{name}" successfully added!', 'success')
            return redirect(url_for('auth.universities'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error pushing record: {e}', 'danger')
            return redirect(url_for('admin.admin_add_university'))

    return render_template('admin_add_university.html', university=None)


@admin_bp.route('/admin/university/<int:id>/quick-edit', methods=['GET', 'POST'])
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
            flash(f'University entity card "{univ.name}" successfully updated!', 'success')
            return redirect(url_for('auth.universities'))
        except Exception as e:
            db.session.rollback()
            return f"Quick edit pipeline error: {e}"

    return render_template('admin_quick_edit_university.html', university=univ)


@admin_bp.route('/admin/university/<int:id>/edit-profile', methods=['GET', 'POST'])
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

        if 'logo' in request.files and request.files['logo'].filename != '':
            univ.logo = save_picture(request.files['logo'])

        try:
            db.session.commit()
            flash(f'Internal university database profile successfully updated!', 'success')
            return redirect(url_for('auth.university_detail', id=univ.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Profile modification exception: {e}', 'danger')
            return redirect(request.url)

    return render_template('admin_add_university.html', university=univ)