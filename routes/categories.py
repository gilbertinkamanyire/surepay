import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from config import Config
from helpers import login_required, role_required, send_notification_email

def register_categories(app):


    @app.route('/categories')
    def categories_list():
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '').strip()
        cat_id = request.args.get('cat', type=int)

        query = '''
            SELECT c.*, u.full_name as admin_name, d.name as system_name,
                   (SELECT COUNT(*) FROM enrollments WHERE category_id = c.id) as student_count,
                   (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as lesson_count
            FROM categories c 
            JOIN users u ON c.admin_id = u.id
            LEFT JOIN systems d ON c.system_id = d.id
            WHERE c.is_published = 1
        '''
        params = []

        if search:
            query += ' AND (c.title LIKE ? OR c.description LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        if cat_id:
            query += ' AND c.system_id = ?'
            params.append(cat_id)

        total = g.db.execute(f'SELECT COUNT(*) FROM categories c WHERE c.is_published = 1' +
                            (' AND (c.title LIKE ? OR c.description LIKE ?)' if search else '') +
                            (' AND c.system_id = ?' if cat_id else ''),
                            params).fetchone()[0]

        per_page = Config.ITEMS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        query += f' ORDER BY c.created_at DESC LIMIT {per_page} OFFSET {offset}'
        categories = g.db.execute(query, params).fetchall()

        # Get systems for filter
        systems = g.db.execute('SELECT * FROM systems ORDER BY name').fetchall()

        return render_template('categories/list.html',
                             categories=categories,
                             systems=systems,
                             page=page,
                             total_pages=total_pages,
                             search=search,
                             current_cat=cat_id)


    @app.route('/categories/<int:category_id>')
    def category_detail(category_id):
        category = g.db.execute('''
            SELECT c.*, u.full_name as admin_name, u.email as lecturer_email, u.bio as lecturer_bio,
                   (SELECT COUNT(*) FROM enrollments WHERE category_id = c.id) as student_count,
                   (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as lesson_count
            FROM categories c JOIN users u ON c.admin_id = u.id
            WHERE c.id = ?
        ''', (category_id,)).fetchone()

        if not category:
            abort(404)

        # Determine if current user is the lecturer of this category or an admin
        is_manage_role = session.get('role') in ('lecturer', 'admin')
        is_owner = (session.get('role') == 'admin' or category['admin_id'] == session.get('user_id'))
        is_instructor = is_manage_role and is_owner

        # Get lessons — employees see all, guests/others see only visible
        lesson_query = '''
            SELECT l.*,
                   (SELECT completed FROM lesson_progress WHERE employee_id = ? AND lesson_id = l.id) as is_completed,
                   (SELECT COUNT(*) FROM assessments WHERE lesson_id = l.id AND category_id = l.category_id) as has_questionnaire
            FROM lessons l WHERE l.category_id = ?
        '''
        # Only hide lessons from unauthenticated / non-employee non-instructor views
        if not is_instructor and session.get('role') not in ('employee',):
            lesson_query += ' AND l.is_hidden = 0'
        
        lesson_query += ' ORDER BY l.order_num'
        lessons = g.db.execute(lesson_query, (session.get('user_id'), category_id)).fetchall()

        enrollment = g.db.execute(
            'SELECT * FROM enrollments WHERE employee_id = ? AND category_id = ?',
            (session.get('user_id'), category_id)
        ).fetchone()

        # Get assessments - filter hidden for students
        assess_query = '''
            SELECT a.*,
                   (SELECT id FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as submission_id,
                   (SELECT score FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as my_score,
                   (SELECT max_score FROM submissions WHERE assessment_id = a.id AND employee_id = ?) as my_max_score
            FROM assessments a WHERE a.category_id = ?
        '''
        if not is_instructor:
            assess_query += ' AND a.is_hidden = 0'
        
        assess_query += ' ORDER BY a.created_at'
        assessments = g.db.execute(assess_query, (session.get('user_id'), session.get('user_id'), session.get('user_id'), category_id)).fetchall()

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
            WHERE d.category_id = ?
            ORDER BY d.created_at DESC LIMIT 5
        ''', (category_id,)).fetchall()

        # Get participants — all enrolled students + the lecturer (visible to all category members)
        participants = g.db.execute('''
            SELECT u.id, u.full_name, u.role, u.profile_pic_url,
                   e.progress, e.participation_points, e.enrolled_at,
                   (SELECT COUNT(*) FROM lesson_progress lp JOIN lessons l ON lp.lesson_id = l.id WHERE lp.employee_id = u.id AND l.category_id = ? AND lp.completed = 1) as lessons_completed,
                   (SELECT COUNT(*) FROM submissions sub JOIN assessments a ON sub.assessment_id = a.id WHERE sub.employee_id = u.id AND a.category_id = ? AND a.lesson_id IS NOT NULL) as quizzes_completed
            FROM enrollments e
            JOIN users u ON e.employee_id = u.id
            WHERE e.category_id = ?
            ORDER BY e.enrolled_at ASC
        ''', (category_id, category_id, category_id)).fetchall()

        return render_template('categories/detail.html',
                             category=category,
                             lessons=lessons,
                             enrollment=enrollment,
                             assessments=assessments,
                             discussions=discussions,
                             participants=participants)


    @app.route('/categories/<int:category_id>/enroll', methods=['POST'])
    @login_required
    def enroll_category(category_id):
        # Make sure the current user still exists (guards against a stale session
        # pointing at a user id that is no longer in the database).
        user = g.db.execute('SELECT id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user:
            session.clear()
            flash('Your session has expired. Please log in again.', 'warning')
            return redirect(url_for('login'))

        # Make sure the category exists before enrolling.
        category = g.db.execute('SELECT id FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            abort(404)

        # Check if already enrolled
        existing = g.db.execute(
            'SELECT id FROM enrollments WHERE employee_id = ? AND category_id = ?',
            (session['user_id'], category_id)
        ).fetchone()

        if not existing:
            g.db.execute(
                'INSERT INTO enrollments (employee_id, category_id) VALUES (?, ?)',
                (session['user_id'], category_id)
            )
            g.db.commit()
            flash('Successfully enrolled in the category!', 'success')
        else:
            flash('You are already enrolled in this category.', 'info')

        return redirect(url_for('category_detail', category_id=category_id))


    @app.route('/categories/<int:category_id>/unenroll', methods=['POST'])
    @login_required
    def unenroll_category(category_id):
        g.db.execute(
            'DELETE FROM enrollments WHERE employee_id = ? AND category_id = ?',
            (session['user_id'], category_id)
        )
        g.db.commit()
        flash('You have been unenrolled from the category.', 'info')
        return redirect(url_for('categories_list'))


    @app.route('/categories/create', methods=['GET', 'POST'])
    @role_required('admin')
    def create_category():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            system_id = request.form.get('system_id', type=int)
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
                unique_filename = f"category_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                image.save(upload_path)
                image_url = f"/uploads/{unique_filename}"

            if not title or not system_id:
                flash('category title and system are required.', 'danger')
            else:
                g.db.execute(
                    'INSERT INTO categories (title, description, admin_id, system_id, image_url, is_published, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (title, description, admin_id, system_id, image_url, is_published, category)
                )
                g.db.commit()
                if is_published:
                    send_notification_email(
                        subject=f"New category Added: {title}",
                        text_part=f"A new category '{title}' has been added.",
                        html_part=f"<h3>New category Added</h3><p>A new category <b>{title}</b> has been published.</p>",
                        notify_roles=['student']
                    )
                flash('category unit created successfully!', 'success')
                return redirect(url_for('dashboard'))

        systems = g.db.execute('SELECT * FROM systems ORDER BY name').fetchall()
        preselect_cat = request.args.get('cat_id', type=int)
        # Allow an explicit trainer/admin id in query params (admin_id or trainer_id)
        preselect_admin = request.args.get('admin_id', type=int) or request.args.get('trainer_id', type=int)

        # Safely check for system_id column (older DBs may not have it)
        has_cat_col = False
        try:
            cols = g.db.execute("PRAGMA table_info(users)").fetchall()
            col_names = [c['name'] for c in cols]
            has_cat_col = 'system_id' in col_names
        except Exception:
            has_cat_col = False

        # Fetch lecturers; if a system is preselected and the column exists, filter lecturers
        if preselect_cat and has_cat_col:
            lecturers = g.db.execute(
                "SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1 AND system_id = ? ORDER BY full_name",
                (preselect_cat,)
            ).fetchall()
        else:
            # Fallback to selecting all active lecturers when filtering isn't possible
            lecturers = g.db.execute(
                "SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1 ORDER BY full_name"
            ).fetchall()

        # Default the selected trainer to the first lecturer in the filtered list when applicable
        if not preselect_admin and preselect_cat and lecturers:
            try:
                preselect_admin = lecturers[0]['id']
            except Exception:
                preselect_admin = None

        return render_template('categories/create.html',
                             systems=systems,
                             lecturers=lecturers,
                             admins=lecturers,
                             preselect_cat=preselect_cat,
                             preselect_admin=preselect_admin)


    @app.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @role_required('admin')
    def edit_category(category_id):
        category = g.db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            abort(404)

        # Only owner or admin
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            system_id = request.form.get('system_id', type=int)
            admin_id = request.form.get('admin_id', type=int)
            # If admin_id is not submitted (selection removed), preserve existing assignment
            if not admin_id:
                admin_id = category['admin_id']
            category = request.form.get('category', 'General').strip()
            is_published = 1 if request.form.get('is_published') else 0

            image_url = category['image_url']
            image = request.files.get('image')
            if image and image.filename:
                from werkzeug.utils import secure_filename
                filename = secure_filename(image.filename)
                unique_filename = f"category_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                image.save(upload_path)
                image_url = f"/uploads/{unique_filename}"

            if title and system_id:
                g.db.execute(
                    'UPDATE categories SET title = ?, description = ?, system_id = ?, admin_id = ?, is_published = ?, image_url = ?, category = ? WHERE id = ?',
                    (title, description, system_id, admin_id, is_published, image_url, category, category_id)
                )
                g.db.commit()
                flash('category unit updated successfully!', 'success')
                return redirect(url_for('category_detail', category_id=category_id))

        systems = g.db.execute('SELECT * FROM systems ORDER BY name').fetchall()
        lecturers = g.db.execute("SELECT id, full_name FROM users WHERE role = 'lecturer' AND is_active = 1").fetchall()
        return render_template('categories/edit.html', category=category, systems=systems, lecturers=lecturers, admins=lecturers)
    @app.route('/lessons/<int:lesson_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_lesson_visibility(lesson_id):
        lesson = g.db.execute('SELECT category_id, is_hidden FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
        if not lesson: abort(404)
        
        category = g.db.execute('SELECT admin_id FROM categories WHERE id = ?', (lesson['category_id'],)).fetchone()
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if lesson['is_hidden'] else 1
        g.db.execute('UPDATE lessons SET is_hidden = ? WHERE id = ?', (new_status, lesson_id))
        g.db.commit()
        flash('Lesson visibility updated.', 'success')
        return redirect(url_for('category_detail', category_id=lesson['category_id']))

    @app.route('/assessments/<int:assessment_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_assessment_visibility(assessment_id):
        assess = g.db.execute('SELECT category_id, is_hidden FROM assessments WHERE id = ?', (assessment_id,)).fetchone()
        if not assess: abort(404)
        
        category = g.db.execute('SELECT admin_id FROM categories WHERE id = ?', (assess['category_id'],)).fetchone()
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if assess['is_hidden'] else 1
        g.db.execute('UPDATE assessments SET is_hidden = ? WHERE id = ?', (new_status, assessment_id))
        g.db.commit()
        flash('Assessment visibility updated.', 'success')
        return redirect(url_for('category_detail', category_id=assess['category_id']))

    @app.route('/assignments/<int:assignment_id>/toggle-visibility', methods=['POST'])
    @login_required
    def toggle_assignment_visibility(assignment_id):
        assign = g.db.execute('SELECT category_id, is_hidden FROM assignments WHERE id = ?', (assignment_id,)).fetchone()
        if not assign: abort(404)
        
        category = g.db.execute('SELECT admin_id FROM categories WHERE id = ?', (assign['category_id'],)).fetchone()
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        new_status = 0 if assign['is_hidden'] else 1
        g.db.execute('UPDATE assignments SET is_hidden = ? WHERE id = ?', (new_status, assignment_id))
        g.db.commit()
        flash('Assignment visibility updated.', 'success')
        return redirect(url_for('category_detail', category_id=assign['category_id']))

    @app.route('/categories/<int:category_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_category(category_id):
        category = g.db.execute('SELECT admin_id, image_url FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category: abort(404)
        
        if session['role'] != 'admin' and category['admin_id'] != session['user_id']:
            abort(403)
            
        # Delete category image if it exists
        if category['image_url'] and category['image_url'].startswith('/uploads/category_'):
            pic_path = os.path.join(app.root_path, 'static', category['image_url'].lstrip('/static/'))
            if os.path.exists(pic_path):
                try: os.remove(pic_path)
                except: pass

        g.db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        g.db.commit()
        flash('category and all its materials have been permanently deleted.', 'warning')
        return redirect(url_for('categories_list'))
