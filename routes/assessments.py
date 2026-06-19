import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from helpers import login_required, role_required, send_notification_email

MAX_ATTEMPTS = 3

def register_assessments(app):


    @app.route('/categories/<int:category_id>/assessments/<int:assessment_id>')
    @login_required
    def take_assessment(category_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND category_id = ?',
            (assessment_id, category_id)
        ).fetchone()

        if not assessment:
            abort(404)

        # Check visibility and expiration for employees
        if session.get('role') == 'employee':
            if assessment['is_hidden']:
                flash('This assessment is currently hidden by the trainer.', 'warning')
                return redirect(url_for('category_detail', category_id=category_id))
            
            if assessment['available_until']:
                try:
                    expiry = datetime.strptime(assessment['available_until'], '%Y-%m-%dT%H:%M')
                    if datetime.now() > expiry:
                        flash('This assessment has expired and is no longer available.', 'danger')
                        return redirect(url_for('category_detail', category_id=category_id))
                except:
                    pass

        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()

        # Check if employee_id is provided (for reviewers)
        employee_id = request.args.get('employee_id', session['user_id'], type=int)
        
        # Security: only admins can see other employees' submissions
        if employee_id != session['user_id'] and session['role'] not in ('lecturer', 'admin'):
            abort(403)

        # Fetch ALL submissions for this employee/assessment (ordered by attempt)
        all_submissions = g.db.execute(
            'SELECT * FROM submissions WHERE assessment_id = ? AND employee_id = ? ORDER BY attempt_number ASC',
            (assessment_id, employee_id)
        ).fetchall()

        attempt_count = len(all_submissions)
        questions = json.loads(assessment['questions_json'])

        # Get the best-scoring submission (for display)
        best_submission = None
        if all_submissions:
            best_submission = max(all_submissions, key=lambda s: (s['score'] / s['max_score']) if s['max_score'] > 0 else 0)

        # If max attempts reached, show score-only results page
        if attempt_count >= MAX_ATTEMPTS:
            return render_template('assessments/results.html',
                                 assessment=assessment,
                                 category=category,
                                 submission=best_submission,
                                 all_submissions=all_submissions,
                                 questions=questions,
                                 answers={},
                                 attempt_count=attempt_count,
                                 max_attempts=MAX_ATTEMPTS,
                                 can_retry=False)

        # If already attempted but can still retry (employee viewing their results)
        if all_submissions and employee_id == session['user_id'] and session['role'] not in ('admin', 'lecturer'):
            last_submission = all_submissions[-1]
            return render_template('assessments/results.html',
                                 assessment=assessment,
                                 category=category,
                                 submission=best_submission,
                                 all_submissions=all_submissions,
                                 questions=questions,
                                 answers={},
                                 attempt_count=attempt_count,
                                 max_attempts=MAX_ATTEMPTS,
                                 can_retry=(attempt_count < MAX_ATTEMPTS))

        # Admin/reviewer: show full results with answer review
        if all_submissions and session['role'] in ('admin', 'lecturer'):
            last_submission = all_submissions[-1]
            answers = json.loads(last_submission['answers_json'])
            return render_template('assessments/results.html',
                                 assessment=assessment,
                                 category=category,
                                 submission=best_submission,
                                 all_submissions=all_submissions,
                                 questions=questions,
                                 answers=answers,
                                 attempt_count=attempt_count,
                                 max_attempts=MAX_ATTEMPTS,
                                 can_retry=False)

        # No submission yet — show the quiz form
        return render_template('assessments/take.html',
                             assessment=assessment,
                             category=category,
                             questions=questions,
                             attempt_count=attempt_count,
                             max_attempts=MAX_ATTEMPTS)


    @app.route('/categories/<int:category_id>/assessments/<int:assessment_id>/submissions')
    @role_required('admin')
    def view_submissions(category_id, assessment_id):
        assessment = g.db.execute('SELECT * FROM assessments WHERE id = ?', (assessment_id,)).fetchone()
        if not assessment:
            abort(404)
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        
        # Get best submission per employee + attempt count
        submissions = g.db.execute('''
            SELECT sub.*, u.full_name, u.username,
                   (SELECT COUNT(*) FROM submissions s2 WHERE s2.assessment_id = sub.assessment_id AND s2.employee_id = sub.employee_id) as attempt_count,
                   (SELECT MAX(s3.score * 1.0 / NULLIF(s3.max_score, 0)) FROM submissions s3 WHERE s3.assessment_id = sub.assessment_id AND s3.employee_id = sub.employee_id) as best_pct
            FROM submissions sub
            JOIN users u ON sub.employee_id = u.id
            WHERE sub.assessment_id = ?
              AND sub.attempt_number = (
                  SELECT MAX(s4.attempt_number) FROM submissions s4
                  WHERE s4.assessment_id = sub.assessment_id AND s4.employee_id = sub.employee_id
              )
            ORDER BY sub.submitted_at DESC
        ''', (assessment_id,)).fetchall()
        
        return render_template('assessments/submissions.html', 
                             assessment=assessment, 
                             category=category, 
                             submissions=submissions)


    @app.route('/categories/<int:category_id>/assessments/<int:assessment_id>/submit', methods=['POST'])
    @login_required
    def submit_assessment(category_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND category_id = ?',
            (assessment_id, category_id)
        ).fetchone()

        if not assessment:
            abort(404)

        # Count existing attempts
        attempt_count = g.db.execute(
            'SELECT COUNT(*) FROM submissions WHERE assessment_id = ? AND employee_id = ?',
            (assessment_id, session['user_id'])
        ).fetchone()[0]

        if attempt_count >= MAX_ATTEMPTS:
            flash(f'You have used all {MAX_ATTEMPTS} attempts for this assessment.', 'danger')
            return redirect(url_for('take_assessment', category_id=category_id, assessment_id=assessment_id))

        questions = json.loads(assessment['questions_json'])
        answers = {}
        score = 0
        max_score = len(questions)

        for i, q in enumerate(questions):
            answer = request.form.get(f'q_{i}', None)
            if answer is not None:
                answer = int(answer)
                answers[str(i)] = answer
                if answer == q['correct']:
                    score += 1

        new_attempt_number = attempt_count + 1

        g.db.execute(
            'INSERT INTO submissions (assessment_id, employee_id, answers_json, score, max_score, attempt_number) VALUES (?, ?, ?, ?, ?, ?)',
            (assessment_id, session['user_id'], json.dumps(answers), score, max_score, new_attempt_number)
        )
        g.db.commit()

        # Badge/certificate logic: use BEST score across all attempts
        total_quizzes = g.db.execute('SELECT COUNT(*) FROM assessments WHERE category_id = ?', (category_id,)).fetchone()[0]
        
        # Get best submission per assessment for this user
        my_best_submissions = g.db.execute('''
            SELECT a.id,
                   MAX(s.score * 1.0 / NULLIF(s.max_score, 0)) as best_ratio,
                   (SELECT s2.max_score FROM submissions s2 WHERE s2.assessment_id = a.id AND s2.employee_id = ? ORDER BY s2.score DESC LIMIT 1) as best_max_score,
                   (SELECT s2.score FROM submissions s2 WHERE s2.assessment_id = a.id AND s2.employee_id = ? ORDER BY s2.score DESC LIMIT 1) as best_score
            FROM assessments a
            JOIN submissions s ON a.id = s.assessment_id AND s.employee_id = ?
            WHERE a.category_id = ?
            GROUP BY a.id
        ''', (session['user_id'], session['user_id'], session['user_id'], category_id)).fetchall()

        assessed_ids = {r['id'] for r in my_best_submissions}
        all_assessment_ids = {r['id'] for r in g.db.execute('SELECT id FROM assessments WHERE category_id = ?', (category_id,)).fetchall()}

        if assessed_ids >= all_assessment_ids and total_quizzes > 0:
            total_score = sum(r['best_score'] for r in my_best_submissions)
            total_max = sum(r['best_max_score'] for r in my_best_submissions)
            if total_max > 0:
                avg_percentage = (total_score / total_max) * 100
                
                badge_type = None
                if avg_percentage >= 90:
                    badge_type = 'golden'
                elif avg_percentage >= 80:
                    badge_type = 'silver'
                elif avg_percentage >= 70:
                    badge_type = 'bronze'
                    
                if badge_type:
                    try:
                        # Upsert: upgrade badge if better performance
                        existing_badge = g.db.execute(
                            'SELECT id, badge_type FROM badges WHERE user_id = ? AND category_id = ?',
                            (session['user_id'], category_id)
                        ).fetchone()
                        
                        badge_rank = {'bronze': 1, 'silver': 2, 'golden': 3}
                        if existing_badge:
                            if badge_rank.get(badge_type, 0) > badge_rank.get(existing_badge['badge_type'], 0):
                                g.db.execute(
                                    'UPDATE badges SET badge_type = ?, awarded_at = CURRENT_TIMESTAMP WHERE id = ?',
                                    (badge_type, existing_badge['id'])
                                )
                                g.db.commit()
                                flash(f'🏅 Your badge has been upgraded to {badge_type.title()}!', 'success')
                        else:
                            g.db.execute(
                                'INSERT INTO badges (user_id, category_id, badge_type) VALUES (?, ?, ?)',
                                (session['user_id'], category_id, badge_type)
                            )
                            g.db.commit()
                            flash(f'🎉 Congratulations! You earned a {badge_type.title()} badge for this category!', 'success')
                    except Exception:
                        pass

        pct = round((score / max_score) * 100) if max_score > 0 else 0
        attempts_left = MAX_ATTEMPTS - new_attempt_number
        if attempts_left > 0:
            flash(f'Submitted! Score: {score}/{max_score} ({pct}%). You have {attempts_left} attempt(s) remaining.', 'success')
        else:
            flash(f'Final attempt submitted! Best score will be used for your certificate.', 'info')

        return redirect(url_for('take_assessment', category_id=category_id, assessment_id=assessment_id))


    @app.route('/categories/<int:category_id>/assessments/create', methods=['GET', 'POST'])
    @role_required('admin')
    def create_assessment(category_id):
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            abort(404)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            time_limit = request.form.get('time_limit', 0, type=int)
            privacy_mode = 1 if request.form.get('privacy_mode') else 0
            lesson_id_raw = request.form.get('lesson_id')
            try:
                lesson_id = int(lesson_id_raw) if lesson_id_raw not in (None, '', 'None') else None
            except:
                lesson_id = None

            # Parse questions from form (Up to 100 slots, Zero-JS)
            questions = []
            for q_index in range(100):
                q_text = request.form.get(f'question_{q_index}', '').strip()
                if not q_text:
                    continue

                options = []
                for o in range(4):
                    opt = request.form.get(f'option_{q_index}_{o}', '').strip()
                    options.append(opt)

                correct = request.form.get(f'correct_{q_index}', 0, type=int)

                questions.append({
                    'question': q_text,
                    'options': options,
                    'correct': correct
                })

            if title and questions:
                # Get local time format for DB
                avail_until = request.form.get('available_until')
                is_hidden = 1 if request.form.get('is_hidden') else 0

                g.db.execute(
                    'INSERT INTO assessments (category_id, lesson_id, title, description, questions_json, time_limit, privacy_mode, is_hidden, available_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (category_id, lesson_id, title, description, json.dumps(questions), time_limit, privacy_mode, is_hidden, avail_until)
                )
                g.db.commit()
                send_notification_email(
                    subject=f"New Assessment Added in {category['title']}",
                    text_part=f"A new assessment '{title}' has been added to {category['title']}.",
                    html_part=f"<h3>New Assessment Added</h3><p>A new assessment <b>{title}</b> has been added to <b>{category['title']}</b>.</p>",
                    notify_roles=['student']
                )
                flash('Assessment created!', 'success')
                return redirect(url_for('category_detail', category_id=category_id))
            else:
                flash('Title and at least one question are required.', 'danger')

        lessons = g.db.execute('SELECT id, title FROM lessons WHERE category_id = ? ORDER BY order_num', (category_id,)).fetchall()
        return render_template('assessments/create.html', category=category, lessons=lessons)

    @app.route('/categories/<int:category_id>/assessments/<int:assessment_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_assessment(category_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND category_id = ?',
            (assessment_id, category_id)
        ).fetchone()
        
        if not assessment:
            abort(404)
        
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        
        # Check permissions
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            time_limit = request.form.get('time_limit', 0, type=int)
            privacy_mode = 1 if request.form.get('privacy_mode') else 0

            lesson_id_raw = request.form.get('lesson_id')
            try:
                lesson_id = int(lesson_id_raw) if lesson_id_raw not in (None, '', 'None') else None
            except:
                lesson_id = None

            # Parse questions from form (Up to 100 slots, Zero-JS)
            questions = []
            for q_index in range(100):
                q_text = request.form.get(f'question_{q_index}', '').strip()
                if not q_text:
                    continue

                options = []
                for o in range(4):
                    opt = request.form.get(f'option_{q_index}_{o}', '').strip()
                    options.append(opt)

                correct = request.form.get(f'correct_{q_index}', 0, type=int)

                questions.append({
                    'question': q_text,
                    'options': options,
                    'correct': correct
                })

            if title and questions:
                avail_until = request.form.get('available_until')
                is_hidden = 1 if request.form.get('is_hidden') else 0

                g.db.execute(
                    'UPDATE assessments SET lesson_id=?, title=?, description=?, questions_json=?, time_limit=?, privacy_mode=?, is_hidden=?, available_until=? WHERE id=?',
                    (lesson_id, title, description, json.dumps(questions), time_limit, privacy_mode, is_hidden, avail_until, assessment_id)
                )
                g.db.commit()
                flash('Assessment updated!', 'success')
                return redirect(url_for('category_detail', category_id=category_id))

        questions = json.loads(assessment['questions_json'])
        lessons = g.db.execute('SELECT id, title FROM lessons WHERE category_id = ? ORDER BY order_num', (category_id,)).fetchall()
        return render_template('assessments/edit.html', assessment=assessment, category=category, questions=questions, lessons=lessons)


    @app.route('/categories/<int:category_id>/assessments/<int:assessment_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_assessment(category_id, assessment_id):
        category = g.db.execute('SELECT admin_id FROM categories WHERE id = ?', (category_id,)).fetchone()
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        g.db.execute('DELETE FROM assessments WHERE id = ? AND category_id = ?', (assessment_id, category_id))
        g.db.commit()
        flash('Assessment deleted.', 'info')
        return redirect(url_for('category_detail', category_id=category_id))

    @app.route('/categories/<int:category_id>/certificate')
    @login_required
    def view_certificate(category_id):
        user_id = session['user_id']
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            abort(404)

        user = g.db.execute('SELECT full_name FROM users WHERE id = ?', (user_id,)).fetchone()

        # Get BEST submission per assessment for this user (best score wins)
        submissions = g.db.execute('''
            SELECT a.id as assessment_id,
                   MAX(s.score) as best_score,
                   s.max_score
            FROM assessments a
            JOIN submissions s ON a.id = s.assessment_id AND s.employee_id = ?
            WHERE a.category_id = ?
            GROUP BY a.id, s.max_score
        ''', (user_id, category_id)).fetchall()

        if not submissions:
            flash('You have not completed any assessments in this category yet.', 'warning')
            return redirect(url_for('category_detail', category_id=category_id))

        total_score = sum(s['best_score'] for s in submissions)
        total_max = sum(s['max_score'] for s in submissions)
        score_pct = round((total_score / total_max) * 100) if total_max > 0 else 0

        # Determine class
        if score_pct >= 90:
            cert_class = 'a'
            cert_label = 'Class A — Distinction'
        elif score_pct >= 80:
            cert_class = 'b'
            cert_label = 'Class B — Merit'
        elif score_pct >= 70:
            cert_class = 'c'
            cert_label = 'Class C — Credit'
        else:
            cert_class = 'participation'
            cert_label = 'Certificate of Participation'

        # Get platform name
        try:
            platform_row = g.db.execute("SELECT value FROM platform_settings WHERE key = 'company_name'").fetchone()
            platform_name = platform_row['value'] if platform_row else 'SurePay'
        except Exception:
            platform_name = 'SurePay'

        return render_template('categories/certificate.html',
                             category=category,
                             user_name=user['full_name'],
                             score_pct=score_pct,
                             cert_class=cert_class,
                             cert_label=cert_label,
                             platform_name=platform_name,
                             award_date=datetime.now().strftime('%B %d, %Y'))
