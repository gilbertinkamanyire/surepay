import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from helpers import login_required, role_required, send_notification_email

def register_assessments(app):


    @app.route('/courses/<int:course_id>/assessments/<int:assessment_id>')
    @login_required
    def take_assessment(course_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND course_id = ?',
            (assessment_id, course_id)
        ).fetchone()

        if not assessment:
            abort(404)

        # Check visibility and expiration for students
        if session.get('role') == 'student':
            if assessment['is_hidden']:
                flash('This assessment is currently hidden by the lecturer.', 'warning')
                return redirect(url_for('course_detail', course_id=course_id))
            
            if assessment['available_until']:
                try:
                    expiry = datetime.strptime(assessment['available_until'], '%Y-%m-%dT%H:%M')
                    if datetime.now() > expiry:
                        flash('This assessment has expired and is no longer available.', 'danger')
                        return redirect(url_for('course_detail', course_id=course_id))
                except:
                    pass

        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

        # Check if employee_id is provided (for reviewers)
        employee_id = request.args.get('employee_id', session['user_id'], type=int)
        
        # Security: only lecturers/admins can see other students' submissions
        if employee_id != session['user_id'] and session['role'] not in ('lecturer', 'admin'):
            abort(403)

        # Check if already submitted
        existing = g.db.execute(
            'SELECT * FROM submissions WHERE assessment_id = ? AND employee_id = ?',
            (assessment_id, employee_id)
        ).fetchone()

        questions = json.loads(assessment['questions_json'])

        if existing:
            answers = json.loads(existing['answers_json'])
            return render_template('assessments/results.html',
                                 assessment=assessment,
                                 course=course,
                                 submission=existing,
                                 questions=questions,
                                 answers=answers)

        return render_template('assessments/take.html',
                             assessment=assessment,
                             course=course,
                             questions=questions)


    @app.route('/courses/<int:course_id>/assessments/<int:assessment_id>/submissions')
    @role_required('admin')
    def view_submissions(course_id, assessment_id):
        assessment = g.db.execute('SELECT * FROM assessments WHERE id = ?', (assessment_id,)).fetchone()
        if not assessment:
            abort(404)
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        
        submissions = g.db.execute('''
            SELECT sub.*, u.full_name, u.username
            FROM submissions sub
            JOIN users u ON sub.employee_id = u.id
            WHERE sub.assessment_id = ?
            ORDER BY sub.submitted_at DESC
        ''', (assessment_id,)).fetchall()
        
        return render_template('assessments/submissions.html', 
                             assessment=assessment, 
                             course=course, 
                             submissions=submissions)


    @app.route('/courses/<int:course_id>/assessments/<int:assessment_id>/submit', methods=['POST'])
    @login_required
    def submit_assessment(course_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND course_id = ?',
            (assessment_id, course_id)
        ).fetchone()

        if not assessment:
            abort(404)

        # Check if already submitted
        existing = g.db.execute(
            'SELECT id FROM submissions WHERE assessment_id = ? AND employee_id = ?',
            (assessment_id, session['user_id'])
        ).fetchone()

        if existing:
            flash('You have already submitted this assessment.', 'warning')
            return redirect(url_for('take_assessment', course_id=course_id, assessment_id=assessment_id))

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

        g.db.execute(
            'INSERT INTO submissions (assessment_id, employee_id, answers_json, score, max_score) VALUES (?, ?, ?, ?, ?)',
            (assessment_id, session['user_id'], json.dumps(answers), score, max_score)
        )
        g.db.commit()

        # Check for course completion badge
        total_quizzes = g.db.execute('SELECT COUNT(*) FROM assessments WHERE course_id = ?', (course_id,)).fetchone()[0]
        
        my_submissions = g.db.execute('''
            SELECT a.id, s.score, s.max_score
            FROM assessments a
            JOIN submissions s ON a.id = s.assessment_id
            WHERE a.course_id = ? AND s.employee_id = ?
        ''', (course_id, session['user_id'])).fetchall()

        if len(my_submissions) == total_quizzes and total_quizzes > 0:
            total_score = sum(s['score'] for s in my_submissions)
            total_max = sum(s['max_score'] for s in my_submissions)
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
                        g.db.execute('''
                            INSERT INTO badges (user_id, course_id, badge_type)
                            VALUES (?, ?, ?)
                        ''', (session['user_id'], course_id, badge_type))
                        g.db.commit()
                        flash(f'Congratulations! You earned a {badge_type.title()} badge for this course!', 'success')
                    except Exception as e:
                        pass # Badge might already exist

        lecturer = g.db.execute('''
            SELECT u.email, u.full_name 
            FROM courses c JOIN users u ON c.admin_id = u.id 
            WHERE c.id = ?
        ''', (course_id,)).fetchone()

        if lecturer:
            send_notification_email(
                subject=f"New Assessment Submission for {assessment['title']}",
                text_part=f"A student ({session.get('full_name')}) has submitted the assessment.",
                html_part=f"<h3>New Submission</h3><p>A student (<b>{session.get('full_name')}</b>) has submitted the assessment <b>{assessment['title']}</b> with a score of {score}/{max_score}.</p>",
                specific_emails=[{"Email": lecturer['email'], "Name": lecturer['full_name']}]
            )

        flash(f'Assessment submitted! Score: {score}/{max_score}', 'success')
        return redirect(url_for('take_assessment', course_id=course_id, assessment_id=assessment_id))


    @app.route('/courses/<int:course_id>/assessments/create', methods=['GET', 'POST'])
    @role_required('admin')
    def create_assessment(course_id):
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
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
                    'INSERT INTO assessments (course_id, lesson_id, title, description, questions_json, time_limit, privacy_mode, is_hidden, available_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (course_id, lesson_id, title, description, json.dumps(questions), time_limit, privacy_mode, is_hidden, avail_until)
                )
                g.db.commit()
                send_notification_email(
                    subject=f"New Assessment Added in {course['title']}",
                    text_part=f"A new assessment '{title}' has been added to {course['title']}.",
                    html_part=f"<h3>New Assessment Added</h3><p>A new assessment <b>{title}</b> has been added to <b>{course['title']}</b>.</p>",
                    notify_roles=['student']
                )
                flash('Assessment created!', 'success')
                return redirect(url_for('course_detail', course_id=course_id))
            else:
                flash('Title and at least one question are required.', 'danger')

        lessons = g.db.execute('SELECT id, title FROM lessons WHERE course_id = ? ORDER BY order_num', (course_id,)).fetchall()
        return render_template('assessments/create.html', course=course, lessons=lessons)

    @app.route('/courses/<int:course_id>/assessments/<int:assessment_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_assessment(course_id, assessment_id):
        assessment = g.db.execute(
            'SELECT * FROM assessments WHERE id = ? AND course_id = ?',
            (assessment_id, course_id)
        ).fetchone()
        
        if not assessment:
            abort(404)
        
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        
        # Check permissions
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
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
                return redirect(url_for('course_detail', course_id=course_id))

        questions = json.loads(assessment['questions_json'])
        lessons = g.db.execute('SELECT id, title FROM lessons WHERE course_id = ? ORDER BY order_num', (course_id,)).fetchall()
        return render_template('assessments/edit.html', assessment=assessment, course=course, questions=questions, lessons=lessons)


    @app.route('/courses/<int:course_id>/assessments/<int:assessment_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_assessment(course_id, assessment_id):
        course = g.db.execute('SELECT admin_id FROM courses WHERE id = ?', (course_id,)).fetchone()
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)
            
        g.db.execute('DELETE FROM assessments WHERE id = ? AND course_id = ?', (assessment_id, course_id))
        g.db.commit()
        flash('Assessment deleted.', 'info')
        return redirect(url_for('course_detail', course_id=course_id))

    @app.route('/courses/<int:course_id>/certificate')
    @login_required
    def view_certificate(course_id):
        user_id = session['user_id']
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            abort(404)

        user = g.db.execute('SELECT full_name FROM users WHERE id = ?', (user_id,)).fetchone()

        # Get all submissions for this course
        submissions = g.db.execute('''
            SELECT s.score, s.max_score
            FROM submissions s
            JOIN assessments a ON s.assessment_id = a.id
            WHERE a.course_id = ? AND s.employee_id = ?
        ''', (course_id, user_id)).fetchall()

        if not submissions:
            flash('You have not completed any assessments in this course yet.', 'warning')
            return redirect(url_for('course_detail', course_id=course_id))

        total_score = sum(s['score'] for s in submissions)
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

        return render_template('courses/certificate.html',
                             course=course,
                             user_name=user['full_name'],
                             score_pct=score_pct,
                             cert_class=cert_class,
                             cert_label=cert_label,
                             platform_name=platform_name,
                             award_date=datetime.now().strftime('%B %d, %Y'))
