import os
import secrets
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash
from helpers import role_required, send_notification_email, send_reset_email

def register_admin(app):


    @app.route('/admin/users')
    @role_required('admin')
    def admin_users():
        role_filter = request.args.get('role', '')
        search = request.args.get('search', '').strip()
        dept_filter = request.args.get('dept', type=int)

        # Fetch departments for the dropdown
        try:
            departments = g.db.execute('SELECT id, name FROM departments ORDER BY name').fetchall()
        except Exception:
            departments = []

        query = 'SELECT u.* FROM users u WHERE 1=1'
        params = []

        if role_filter:
            query += ' AND u.role = ?'
            params.append(role_filter)

        if search:
            query += ' AND (u.full_name LIKE ? OR u.username LIKE ? OR u.email LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

        if dept_filter:
            # Filter employees whose enrolled courses belong to the selected department
            query += ''' AND u.id IN (
                SELECT DISTINCT e.employee_id FROM enrollments e
                JOIN courses c ON e.course_id = c.id
                WHERE c.department_id = ?
            )'''
            params.append(dept_filter)

        query += ' ORDER BY u.created_at DESC'
        users = g.db.execute(query, params).fetchall()

        return render_template('admin/users.html', users=users, role_filter=role_filter,
                               search=search, departments=departments, dept_filter=dept_filter)


    @app.route('/admin/users/<int:user_id>/verify', methods=['POST'])
    @role_required('admin')
    def verify_admin(user_id):
        user = g.db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user and user['role'] == 'admin':
            g.db.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user_id,))
            g.db.commit()
            flash('Admin verified successfully.', 'success')

            # Notify the admin
            send_notification_email(
                subject="Account Verified: Admin Access Granted",
                text_part="Your admin account has been verified. You can now log in and manage courses.",
                html_part="<h3>Account Verified</h3><p>Your admin account has been verified. You can now log in and manage courses.</p>",
                specific_emails=[{"Email": user['email'], "Name": user['full_name']}] if 'email' in user.keys() else []
            )
        return redirect(url_for('admin_users'))


    @app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
    @role_required('admin')
    def toggle_user(user_id):
        if user_id == session['user_id']:
            flash('Cannot deactivate your own account. Use the profile delete option if available!', 'danger')
        else:
            user = g.db.execute('SELECT is_active FROM users WHERE id = ?', (user_id,)).fetchone()
            if user:
                new_status = 0 if user['is_active'] else 1
                g.db.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
                g.db.commit()
                flash(f'User {"activated" if new_status else "deactivated"} successfully.', 'success')

        return redirect(url_for('admin_users'))

    @app.route('/admin/users/add', methods=['POST'])
    @role_required('admin')
    def admin_add_user():
        fullname = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'student')
        
        if not (fullname and username and email and password):
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin_users'))
        
        try:
            g.db.execute(
                'INSERT INTO users (full_name, username, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
                (fullname, username, email, generate_password_hash(password), role)
            )
            g.db.commit()
            flash(f'User {username} added successfully.', 'success')
        except Exception as e:
            flash(f'Error adding user: {str(e)}', 'danger')
            
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @role_required('admin')
    def admin_delete_user(user_id):
        if user_id == session['user_id']:
            flash('You cannot delete your own admin account through this panel.', 'danger')
            return redirect(url_for('admin_users'))
            
        try:
            user = g.db.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
            if not user:
                return redirect(url_for('admin_users'))
                
            if user['role'] == 'lecturer' or user['role'] == 'admin':
                courses = g.db.execute('SELECT id FROM courses WHERE admin_id = ?', (user_id,)).fetchall()
                for c in courses:
                    cid = c['id']
                    g.db.execute('DELETE FROM lessons WHERE course_id=?', (cid,))
                    g.db.execute('DELETE FROM submissions WHERE assessment_id IN (SELECT id FROM assessments WHERE course_id=?)', (cid,))
                    g.db.execute('DELETE FROM assessments WHERE course_id=?', (cid,))
                    g.db.execute('DELETE FROM enrollments WHERE course_id=?', (cid,))
                    g.db.execute('DELETE FROM attendance WHERE course_id=?', (cid,))
                    g.db.execute('DELETE FROM discussions WHERE course_id=?', (cid,))
                g.db.execute('DELETE FROM courses WHERE admin_id = ?', (user_id,))
                
            g.db.execute('DELETE FROM discussions WHERE user_id = ?', (user_id,))
            g.db.execute('DELETE FROM replies WHERE user_id = ?', (user_id,))
            g.db.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
            g.db.execute('DELETE FROM announcements WHERE user_id = ?', (user_id,))
            g.db.execute('DELETE FROM enrollments WHERE employee_id = ?', (user_id,))
            g.db.execute('DELETE FROM lesson_progress WHERE employee_id = ?', (user_id,))
            g.db.execute('DELETE FROM submissions WHERE employee_id = ?', (user_id,))
            g.db.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
            try: g.db.execute('DELETE FROM learning_insights WHERE user_id = ?', (user_id,))
            except: pass
            
            g.db.execute('DELETE FROM users WHERE id = ?', (user_id,))
            g.db.commit()
            flash('User and all associated data deleted permanently.', 'warning')
        except Exception as e:
            flash(f'Error deleting user: {str(e)}', 'danger')
            
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/password', methods=['POST'])
    @role_required('admin')
    def admin_edit_password(user_id):
        new_pass = request.form.get('new_password', '')
        confirm_pass = request.form.get('confirm_password', '')
        
        if not new_pass or len(new_pass) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('admin_users'))
            
        if new_pass != confirm_pass:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('admin_users'))
            
        g.db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new_pass), user_id))
        g.db.commit()
        flash('User password updated.', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/send-reset', methods=['POST'])
    @role_required('admin')
    def admin_send_reset(user_id):
        user = g.db.execute('SELECT id, full_name, email FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expiry = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            g.db.execute('UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?',
                       (token, expiry, user_id))
            g.db.commit()
            
            reset_link = url_for('reset_password', token=token, _external=True)
            send_reset_email(user['email'], user['full_name'], reset_link)
            flash(f'Password reset link sent to {user["full_name"]}.', 'success')
        else:
            flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/clear/<role>', methods=['POST'])
    @role_required('admin')
    def admin_clear_role(role):
        if role not in ['student', 'lecturer']:
            flash('Invalid role specified.', 'danger')
            return redirect(url_for('admin_users'))

        # Get all users of this role (excluding admin just in case)
        users = g.db.execute('SELECT id, profile_pic_url FROM users WHERE role = ? AND username != "admin"', (role,)).fetchall()
        user_ids = [u['id'] for u in users]
        
        if not user_ids:
            flash(f'No users with role {role} found to clear.', 'info')
            return redirect(url_for('admin_users'))

        # Bulk cleanup related data
        placeholders = ', '.join(['?'] * len(user_ids))
        
        # Cleanup foreign key tables
        g.db.execute(f'DELETE FROM enrollments WHERE employee_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM lesson_progress WHERE employee_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM submissions WHERE employee_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM attendance WHERE user_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM notifications WHERE user_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM replies WHERE user_id IN ({placeholders})', user_ids)
        g.db.execute(f'DELETE FROM learning_insights WHERE user_id IN ({placeholders})', user_ids)
        
        if role == 'admin':
            # Handle lecturer's courses
            courses = g.db.execute(f'SELECT id FROM courses WHERE admin_id IN ({placeholders})', user_ids).fetchall()
            if courses:
                course_ids = [c['id'] for c in courses]
                c_placeholders = ', '.join(['?'] * len(course_ids))
                g.db.execute(f'DELETE FROM courses WHERE id IN ({c_placeholders})', course_ids)

        # Delete users
        g.db.execute(f'DELETE FROM users WHERE id IN ({placeholders})', user_ids)
        g.db.commit()

        # Try to delete profile pics after commit
        for u in users:
            if u['profile_pic_url'] and u['profile_pic_url'].startswith('/uploads/avatar_'):
                pic_path = os.path.join(app.root_path, u['profile_pic_url'].lstrip('/'))
                if os.path.exists(pic_path):
                    try: os.remove(pic_path)
                    except: pass

        flash(f'All {role} accounts and associated data have been cleared.', 'warning')
        return redirect(url_for('admin_users'))


    @app.route('/admin/courses/<int:course_id>/clear-enrollments', methods=['POST'])
    @role_required('admin')
    def admin_clear_course_enrollments(course_id):
        g.db.execute('DELETE FROM enrollments WHERE course_id = ?', (course_id,))
        g.db.execute('DELETE FROM lesson_progress WHERE lesson_id IN (SELECT id FROM lessons WHERE course_id = ?)', (course_id,))
        g.db.execute('DELETE FROM submissions WHERE assessment_id IN (SELECT id FROM assessments WHERE course_id = ?)', (course_id,))
        g.db.commit()
        flash('All student enrollments and progress for this course have been cleared.', 'warning')
        return redirect(request.referrer or url_for('admin_analytics'))


    @app.route('/admin/announcements', methods=['GET', 'POST'])
    @role_required('admin')
    def manage_announcements():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            target = request.form.get('target_role', 'all')

            if title and content:
                g.db.execute(
                    'INSERT INTO announcements (user_id, title, content, target_role) VALUES (?, ?, ?, ?)',
                    (session['user_id'], title, content, target)
                )
                g.db.commit()
                roles_to_notify = ['student', 'lecturer'] if target == 'all' else [target]
                send_notification_email(
                    subject=f"New Announcement: {title}",
                    text_part=content,
                    html_part=f"<h3>{title}</h3><p>{content}</p>",
                    notify_roles=roles_to_notify
                )
                flash('Announcement posted!', 'success')

        announcements = g.db.execute('''
            SELECT a.*, u.full_name as author_name
            FROM announcements a JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
        ''').fetchall()

        return render_template('admin/announcements.html', announcements=announcements)


    @app.route('/admin/analytics')
    @role_required('admin')
    def admin_analytics():
        stats = {
            'total_users': g.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'students': g.db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
            'lecturers': g.db.execute("SELECT COUNT(*) FROM users WHERE role='lecturer'").fetchone()[0],
            'courses': g.db.execute('SELECT COUNT(*) FROM courses').fetchone()[0],
            'published_courses': g.db.execute('SELECT COUNT(*) FROM courses WHERE is_published=1').fetchone()[0],
            'enrollments': g.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0],
            'lessons': g.db.execute('SELECT COUNT(*) FROM lessons').fetchone()[0],
            'discussions': g.db.execute('SELECT COUNT(*) FROM discussions').fetchone()[0],
            'submissions': g.db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],
        }

        # Top courses by enrollment
        top_courses = g.db.execute('''
            SELECT c.title, COUNT(e.id) as enrollments
            FROM courses c LEFT JOIN enrollments e ON c.id = e.course_id
            GROUP BY c.id ORDER BY enrollments DESC LIMIT 10
        ''').fetchall()

        # Users by role
        roles = g.db.execute('''
            SELECT role, COUNT(*) as count FROM users GROUP BY role
        ''').fetchall()

        return render_template('admin/analytics.html', stats=stats, top_courses=top_courses, roles=roles)


    @app.route('/admin/employee-progress')
    @role_required('admin')
    def admin_employee_progress():
        search = request.args.get('search', '').strip()
        dept_filter = request.args.get('dept', type=int)
        try:
            departments = g.db.execute('SELECT id, name FROM departments ORDER BY name').fetchall()
        except Exception:
            departments = []

        total_employees = 0
        completed_count = 0
        records = []
        try:
            total_employees = g.db.execute("SELECT COUNT(*) FROM users WHERE role = 'employee'").fetchone()[0]
        except Exception:
            total_employees = 0

        try:
            q = '''
                SELECT u.full_name, u.email,
                       d.name AS system_name,
                       c.title AS course_title,
                       e.progress AS progress,
                       e.enrolled_at AS enrolled_at,
                       (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as total_lessons,
                       (SELECT COUNT(*) FROM lesson_progress lp JOIN lessons l ON lp.lesson_id = l.id WHERE lp.employee_id = u.id AND l.course_id = c.id AND lp.completed = 1) as completed_lessons,
                       (SELECT awarded_at FROM badges WHERE user_id = u.id AND course_id = c.id ORDER BY awarded_at DESC LIMIT 1) as badge_date
                FROM enrollments e
                JOIN users u ON e.employee_id = u.id
                LEFT JOIN courses c ON e.course_id = c.id
                LEFT JOIN departments d ON c.department_id = d.id
                WHERE 1=1
            '''
            params = []
            if search:
                q += ' AND (u.full_name LIKE ? OR u.email LIKE ?)'
                params.extend([f'%{search}%', f'%{search}%'])
            if dept_filter:
                q += ' AND d.id = ?'
                params.append(dept_filter)
            q += ' ORDER BY u.full_name, c.title'
            records = g.db.execute(q, params).fetchall()

            try:
                completed_count = g.db.execute('SELECT COUNT(*) FROM badges').fetchone()[0]
            except Exception:
                completed_count = 0
        except Exception:
            records = []

        return render_template('admin/employee_progress.html',
                               total_employees=total_employees,
                               completed_count=completed_count,
                               records=records,
                               departments=departments,
                               dept_filter=dept_filter,
                               search=search)


    @app.route('/admin/settings', methods=['GET', 'POST'])
    @role_required('admin')
    def admin_settings():
        current_settings = {}
        try:
            rows = g.db.execute('SELECT key, value FROM platform_settings').fetchall()
            current_settings = {r['key']: r['value'] for r in rows}
        except Exception:
            current_settings = {}

        if request.method == 'POST':
            company_name = request.form.get('company_name', '').strip()
            primary_color = request.form.get('primary_color', '').strip()
            secondary_color = request.form.get('secondary_color', '').strip()
            logo_file = request.files.get('logo_file')
            try:
                if company_name:
                    g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('company_name', company_name))
                if primary_color:
                    g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('primary_color', primary_color))
                if secondary_color:
                    g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('secondary_color', secondary_color))
                if logo_file and logo_file.filename:
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(logo_file.filename)
                    unique_filename = f"settings_{secrets.token_hex(8)}_{filename}"
                    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'].lstrip('/'), unique_filename) if app.config.get('UPLOAD_FOLDER', '').startswith('/') else os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    # Ensure upload folder exists
                    os.makedirs(app.config.get('UPLOAD_FOLDER', '.'), exist_ok=True)
                    logo_file.save(os.path.join(app.config.get('UPLOAD_FOLDER', '.'), unique_filename))
                    logo_url = f"/uploads/{unique_filename}"
                    g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('logo_url', logo_url))

                # Terms & Conditions — save content and bump the version when it changes
                # (bumping the version forces every user to re-accept on their next request).
                terms_content = request.form.get('terms_content')
                if terms_content is not None:
                    terms_content = terms_content.strip()
                    old_terms = current_settings.get('terms_content', '')
                    if terms_content != old_terms:
                        g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('terms_content', terms_content))
                        try:
                            new_version = str(int(current_settings.get('terms_version', '1')) + 1)
                        except (TypeError, ValueError):
                            new_version = '1'
                        g.db.execute('INSERT OR REPLACE INTO platform_settings (key, value) VALUES (?, ?)', ('terms_version', new_version))
                        flash(f'Terms updated to version {new_version}. All users will be asked to re-accept.', 'info')

                g.db.commit()
                flash('Settings saved.', 'success')
            except Exception as e:
                flash(f'Error saving settings: {e}', 'danger')
            return redirect(url_for('admin_settings'))

        return render_template('admin/settings.html', current_settings=current_settings)


    @app.route('/admin/clear-student-dashboards', methods=['POST'])
    @role_required('admin')
    def admin_clear_student_dashboards():
        """Clear all student dashboard data: enrollments, progress, submissions, attendance."""
        try:
            g.db.execute('DELETE FROM lesson_progress')
            g.db.execute('DELETE FROM submissions')
            g.db.execute('DELETE FROM enrollments')
            g.db.execute('DELETE FROM attendance WHERE user_id IN (SELECT id FROM users WHERE role = "student")')
            g.db.commit()
            flash('All student dashboard data (enrollments, progress, submissions, attendance) has been cleared.', 'warning')
        except Exception as e:
            flash(f'Error clearing student data: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


    # Backwards-compatible wrapper: template uses admin_clear_employee_dashboards
    @app.route('/admin/clear-employee-dashboards', methods=['POST'])
    @role_required('admin')
    def admin_clear_employee_dashboards():
        return admin_clear_student_dashboards()


    @app.route('/admin/clear-lecturer-dashboards', methods=['POST'])
    @role_required('admin')
    def admin_clear_lecturer_dashboards():
        """Clear all lecturer dashboard data: courses, lessons, assessments, assignments, discussions."""
        try:
            # Delete in dependency order
            g.db.execute('DELETE FROM assignment_submissions')
            g.db.execute('DELETE FROM submissions')
            g.db.execute('DELETE FROM lesson_progress')
            g.db.execute('DELETE FROM enrollments')
            g.db.execute('DELETE FROM replies')
            g.db.execute('DELETE FROM discussions')
            g.db.execute('DELETE FROM attendance')
            g.db.execute('DELETE FROM assessments')
            g.db.execute('DELETE FROM assignments')
            g.db.execute('DELETE FROM lessons')
            g.db.execute('DELETE FROM courses')
            g.db.commit()
            flash('All lecturer dashboard data (courses, lessons, assessments, assignments, discussions) has been cleared.', 'warning')
        except Exception as e:
            flash(f'Error clearing lecturer data: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


    # Backwards-compatible wrapper: template uses admin_clear_admin_dashboards
    @app.route('/admin/clear-admin-dashboards', methods=['POST'])
    @role_required('admin')
    def admin_clear_admin_dashboards():
        return admin_clear_lecturer_dashboards()

