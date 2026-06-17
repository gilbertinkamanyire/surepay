import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from config import Config
from helpers import login_required, role_required, send_notification_email

def register_courses(app):


    @app.route('/courses')
    def courses_list():
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '').strip()
        dept_id = request.args.get('dept', type=int)

        query = '''
            SELECT c.*, u.full_name as admin_name, d.name as department_name,
                   (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as student_count,
                   (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as lesson_count
            FROM courses c 
            JOIN users u ON c.admin_id = u.id
            LEFT JOIN departments d ON c.department_id = d.id
            WHERE c.is_published = 1
        '''
        params = []

        if search:
            query += ' AND (c.title LIKE ? OR c.description LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        if dept_id:
            query += ' AND c.department_id = ?'
            params.append(dept_id)

        total = g.db.execute(f'SELECT COUNT(*) FROM courses c WHERE c.is_published = 1' +
                            (' AND (c.title LIKE ? OR c.description LIKE ?)' if search else '') +
                            (' AND c.department_id = ?' if dept_id else ''),
                            params).fetchone()[0]

        per_page = Config.ITEMS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        query += f' ORDER BY c.created_at DESC LIMIT {per_page} OFFSET {offset}'
        courses = g.db.execute(query, params).fetchall()

        # Get departments for filter
        departments = g.db.execute('SELECT * FROM departments ORDER BY name').fetchall()

        return render_template('courses/list.html',
                             courses=courses,
                             departments=departments,
                             page=page,
                             total_pages=total_pages,
                             search=search,
                             current_dept=dept_id)


    @app.route('/courses/<int:course_id>')
    def course_detail(course_id):
        course = g.db.execute('''
            SELECT c.*, u.full_name as admin_name, u.email as lecturer_email, u.bio as lecturer_bio,
                   (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as student_count,
                   (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as lesson_count
            FROM courses c JOIN users u ON c.admin_id = u.id
            WHERE c.id = ?
        ''', (course_id,)).fetchone()

        if not course:
            abort(404)

        # Determine if current user is the lecturer of this course or an admin
        is_manage_role = session.get('role') in ('lecturer', 'admin')
        is_owner = (session.get('role') == 'admin' or course['admin_id'] == session.get('user_id'))
        is_instructor = is_manage_role and is_owner

        # Get lessons — employees see all, guests/others see only visible
        lesson_query = '''
            SELECT l.*,
                   (SELECT completed FROM lesson_progress WHERE employee_id = ? AND lesson_id = l.id) as is_completed,
                   (SELECT COUNT(*) FROM assessments WHERE lesson_id = l.id AND course_id = l.course_id) as has_questionnaire
            FROM lessons l WHERE l.course_id = ?
        '''
        # Only hide lessons from unauthenticated / non-employee non-instructor views
        if not is_instructor and session.get('role') not in ('employee',):
            lesson_query += ' AND l.is_hidden = 0'
        
        lesson_query += ' ORDER BY l.order_num'
        lessons = g.db.execute(lesson_query, (session.get('user_id'), course_id)).fetchall()

        enrollment = g.db.execute(
            'SELECT * FROM enrollments WHERE employee_id = ? AND course_id = ?',
            (session.get('user_id'), course_id)
        ).fetchone()

        # Get assessments - filter hidden for students
        assess_query = '''
            SELECT a.*,
                   (SELECT id FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as submission_id,
                   (SELECT score FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as my_score,
                   (SELECT max_score FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as my_max_score
            FROM assessments a WHERE a.course_id = ?
        '''
        if not is_instructor:
            assess_query += ' AND a.is_hidden = 0'
        
        assess_query += ' ORDER BY a.created_at'
        assessments = g.db.execute(assess_query, (session.get('user_id'), session.get('user_id'), session.get('user_id'), course_id)).fetchall()

        # Add expiration info to assessments
        processed_assessments = []
        for a in assessments:
            a_dict = dict(a)
            a_dict['is_expired'] = False
            if a['available_until']:
                try:
                    expiry = datetime.strptime(a['available_until'], '%Y-%m-%dT%H:%M')
                    if datetime.now() > expiry:
                        a_dict['is_expired'] = True
                except:
                    pass
            processed_assessments.append(a_dict)
        assessments = processed_assessments

        # Get discussions
        discussions = g.db.execute('''
            SELECT d.*, u.full_name as author_name,
                   (SELECT COUNT(*) FROM replies WHERE discussion_id = d.id) as reply_count
            FROM discussions d JOIN users u ON d.user_id = u.id
            WHERE d.course_id = ?
            ORDER BY d.created_at DESC LIMIT 5
        ''', (course_id,)).fetchall()

        # Get participants — all enrolled students + the lecturer (visible to all course members)
        participants = g.db.execute('''
            SELECT u.id, u.full_name, u.role, u.profile_pic_url,
                   e.progress, e.participation_points, e.enrolled_at,
                   (SELECT COUNT(*) FROM lesson_progress lp JOIN lessons l ON lp.lesson_id = l.id WHERE lp.employee_id = u.id AND l.course_id = ? AND lp.completed = 1) as lessons_completed,
                   (SELECT COUNT(*) FROM submissions sub JOIN assessments a ON sub.assessment_id = a.id WHERE sub.employee_id = u.id AND a.course_id = ? AND a.lesson_id IS NOT NULL) as quizzes_completed
            FROM enrollments e
            JOIN users u ON e.employee_id = u.id
            WHERE e.course_id = ?
            ORDER BY e.enrolled_at ASC
        ''', (course_id, course_id, course_id)).fetchall()

        return render_template('courses/detail.html',
                             course=course,
                             lessons=lessons,
                             enrollment=enrollment,
                             assessments=assessments,
                             discussions=discussions,
                             participants=participants)


    @app.route('/courses/<int:course_id>/enroll', methods=['POST'])
    @login_required
    def enroll_course(course_id):
        # Make sure the current user still exists (guards against a stale session
        # pointing at a user id that is no longer in the database).
        user = g.db.execute('SELECT id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user:
            session.clear()
            flash('Your session has expired. Please log in again.', 'warning')
            return redirect(url_for('login'))

        # Make sure the course exists before enrolling.
        course = g.db.execute('SELECT id FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            abort(404)

        # Check if already enrolled
        existing = g.db.execute(
            'SELECT id FROM enrollments WHERE employee_id = ? AND course_id = ?',
            (session['user_id'], course_id)
        ).fetchone()

        if not existing:
            g.db.execute(
                'INSERT INTO enrollments (employee_id, course_id) VALUES (?, ?)',
                (session['user_id'], course_id)
            )
            g.db.commit()
            flash('Successfully enrolled in the course!', 'success')
        else:
            flash('You are already enrolled in this course.', 'info')

        return redirect(url_for('course_detail', course_id=course_id))


    @app.route('/courses/<int:course_id>/unenroll', methods=['POST'])
    @login_required
    def unenroll_course(course_id):
        g.db.execute(
            'DELETE FROM enrollments WHERE employee_id = ? AND course_id = ?',
            (session['user_id'], course_id)
        )
        g.db.commit()
        flash('You have been unenrolled from the course.', 'info')
        return redirect(url_for('courses_list'))


    @app.route('/courses/create', methods=['GET', 'POST'])
    @role_required('admin')
    def create_course():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            department_id = request.form.get('department_id', type=int)
            admin_id = request.form.get('admin_id', type=int)
            # Default admin_id to the current admin (session user) when selection removed
            if not admin_id:
                admin_id = session.get('user_id')
            category = request.form.get('category', 'General').strip()
            is_published = 1 if request.form.get('is_published') else 0

            image_url = ''
            image = request.files.get('image')
            if image and image.filename:
                from werkzeug.utils import secure_filename
                filename = secure_filename(image.filename)
                unique_filename = f"course_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                image.save(upload_path)
                image_url = f"/uploads/{unique_filename}"

            if not title or not department_id:
                flash('Course title and department are required.', 'danger')
            else:
                g.db.execute(
                    'INSERT INTO courses (title, description, admin_id, department_id, image_url, is_published, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (title, description, admin_id, department_id, image_url, is_published, category)
                )
                g.db.commit()
                if is_published:
                    send_notification_email(
                        subject=f"New Course Added: {title}",
                        text_part=f"A new course '{title}' has been added.",
                        html_part=f"<h3>New Course Added</h3><p>A new course <b>{title}</b> has been published.</p>",
                        notify_roles=['student']
                    )
                flash('Course unit created successfully!', 'success')
                return redirect(url_for('dashboard'))

        departments = g.db.execute('SELECT * FROM departments ORDER BY name').fetchall()
        preselect_dept = request.args.get('dept_id', type=int)
        # Allow an explicit trainer/admin id in query params (admin_id or trainer_id)
        preselect_admin = request.args.get('admin_id', type=int) or request.args.get('trainer_id', type=int)

        # Safely check for department_id column (older DBs may not have it)
        has_dept_col = False
        try:
            cols = g.db.execute("PRAGMA table_info(users)").fetchall()
            col_names = [c['name'] for c in cols]
            has_dept_col = 'department_id' in col_names
        except Exception:
            has_dept_col = False

        # Fetch lecturers; if a department is preselected and the column exists, filter lecturers
        if preselect_dept and has_dept_col:
            lecturers = g.db.execute(
                "SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1 AND department_id = ? ORDER BY full_name",
                (preselect_dept,)
            ).fetchall()
        else:
            # Fallback to selecting all active lecturers when filtering isn't possible
            lecturers = g.db.execute(
                "SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1 ORDER BY full_name"
            ).fetchall()

        # Default the selected trainer to the first lecturer in the filtered list when applicable
        if not preselect_admin and preselect_dept and lecturers:
            try:
                preselect_admin = lecturers[0]['id']
            except Exception:
                preselect_admin = None

        return render_template('courses/create.html',
                             departments=departments,
                             lecturers=lecturers,
                             admins=lecturers,
                             preselect_dept=preselect_dept,
                             preselect_admin=preselect_admin)


    @app.route('/courses/<int:course_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_course(course_id):
        course = g.db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            abort(404)

        # Only owner or admin
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            department_id = request.form.get('department_id', type=int)
            admin_id = request.form.get('admin_id', type=int)
            # If admin_id is not submitted (selection removed), preserve existing assignment
            if not admin_id:
                admin_id = course['admin_id']
            category = request.form.get('category', 'General').strip()
            is_published = 1 if request.form.get('is_published') else 0

            image_url = course['image_url']
            image = request.files.get('image')
            if image and image.filename:
                from werkzeug.utils import secure_filename
                filename = secure_filename(image.filename)
                unique_filename = f"course_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                image.save(upload_path)
                image_url = f"/uploads/{unique_filename}"

            if title and department_id:
                g.db.execute(
                    'UPDATE courses SET title = ?, description = ?, department_id = ?, admin_id = ?, is_published = ?, image_url = ?, category = ? WHERE id = ?',
                    (title, description, department_id, admin_id, is_published, image_url, category, course_id)
                )
                g.db.commit()
                flash('Course unit updated successfully!', 'success')
                return redirect(url_for('course_detail', course_id=course_id))

        departments = g.db.execute('SELECT * FROM departments ORDER BY name').fetchall()
        lecturers = g.db.execute("SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1").fetchall()
        return render_template('courses/edit.html', course=course, departments=departments, lecturers=lecturers, admins=lecturers)
    @app.route('/lessons/<int:lesson_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_lesson_visibility(lesson_id):
        lesson = g.db.execute('SELECT course_id, is_hidden FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
        if not lesson: abort(404)
        
        course = g.db.execute('SELECT admin_id FROM courses WHERE id = ?', (lesson['course_id'],)).fetchone()
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if lesson['is_hidden'] else 1
        g.db.execute('UPDATE lessons SET is_hidden = ? WHERE id = ?', (new_status, lesson_id))
        g.db.commit()
        flash('Lesson visibility updated.', 'success')
        return redirect(url_for('course_detail', course_id=lesson['course_id']))

    @app.route('/assessments/<int:assessment_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_assessment_visibility(assessment_id):
        assess = g.db.execute('SELECT course_id, is_hidden FROM assessments WHERE id = ?', (assessment_id,)).fetchone()
        if not assess: abort(404)
        
        course = g.db.execute('SELECT admin_id FROM courses WHERE id = ?', (assess['course_id'],)).fetchone()
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if assess['is_hidden'] else 1
        g.db.execute('UPDATE assessments SET is_hidden = ? WHERE id = ?', (new_status, assessment_id))
        g.db.commit()
        flash('Assessment visibility updated.', 'success')
        return redirect(url_for('course_detail', course_id=assess['course_id']))

    @app.route('/assignments/<int:assignment_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_assignment_visibility(assignment_id):
        assign = g.db.execute('SELECT course_id, is_hidden FROM assignments WHERE id = ?', (assignment_id,)).fetchone()
        if not assign: abort(404)
        
        course = g.db.execute('SELECT admin_id FROM courses WHERE id = ?', (assign['course_id'],)).fetchone()
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if assign['is_hidden'] else 1
        g.db.execute('UPDATE assignments SET is_hidden = ? WHERE id = ?', (new_status, assignment_id))
        g.db.commit()
        flash('Assignment visibility updated.', 'success')
        return redirect(url_for('course_detail', course_id=assign['course_id']))

    @app.route('/courses/<int:course_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_course(course_id):
        course = g.db.execute('SELECT admin_id, image_url FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course: abort(404)
        
        if session['role'] != 'admin' and course['admin_id'] != session['user_id']:
            abort(403)
            
        # Delete course image if it exists
        if course['image_url'] and course['image_url'].startswith('/uploads/course_'):
            pic_path = os.path.join(app.root_path, 'static', course['image_url'].lstrip('/static/'))
            if os.path.exists(pic_path):
                try: os.remove(pic_path)
                except: pass

        g.db.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        g.db.commit()
        flash('Course and all its materials have been permanently deleted.', 'warning')
        return redirect(url_for('courses_list'))
