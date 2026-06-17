import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import login_required

def register_profile(app):


    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        user = g.db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            bio = request.form.get('bio', '').strip()

            # Check email uniqueness
            existing = g.db.execute(
                'SELECT id FROM users WHERE email = ? AND id != ?',
                (email, session['user_id'])
            ).fetchone()

            if existing:
                flash('Email already in use by another user.', 'danger')
            elif full_name and email:
                # Handle profile picture
                profile_pic = request.files.get('profile_pic')
                profile_pic_url = user['profile_pic_url']
                
                if profile_pic and profile_pic.filename:
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(profile_pic.filename)
                    unique_filename = f"avatar_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    profile_pic.save(upload_path)
                    profile_pic_url = f"/uploads/{unique_filename}"

                g.db.execute(
                    'UPDATE users SET full_name=?, email=?, phone=?, bio=?, profile_pic_url=? WHERE id=?',
                    (full_name, email, phone, bio, profile_pic_url, session['user_id'])
                )
                g.db.commit()
                session['full_name'] = full_name
                flash('Profile updated!', 'success')
                return redirect(url_for('profile'))

        # Get user stats
        if user['role'] == 'student':
            stats = {
                'enrolled_courses': g.db.execute(
                    'SELECT COUNT(*) FROM enrollments WHERE employee_id = ?', (user['id'],)
                ).fetchone()[0],
                'completed_lessons': g.db.execute(
                    'SELECT COUNT(*) FROM lesson_progress WHERE employee_id = ? AND completed = 1', (user['id'],)
                ).fetchone()[0],
                'assessments_taken': g.db.execute(
                    'SELECT COUNT(*) FROM submissions WHERE employee_id = ?', (user['id'],)
                ).fetchone()[0],
            }
        elif user['role'] == 'lecturer':
            stats = {
                'courses_created': g.db.execute(
                    'SELECT COUNT(*) FROM courses WHERE admin_id = ?', (user['id'],)
                ).fetchone()[0],
                'total_students': g.db.execute('''
                    SELECT COUNT(DISTINCT e.employee_id) FROM enrollments e
                    JOIN courses c ON e.course_id = c.id
                    WHERE c.admin_id = ?
                ''', (user['id'],)).fetchone()[0],
            }
        else:
            stats = {}

        return render_template('profile.html', user=user, stats=stats)


    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        user = g.db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if request.method == 'POST':
            # Notification settings or other preferences could be handled here
            flash('Settings updated successfully!', 'success')
            return redirect(url_for('settings'))
        return render_template('pages/settings.html', user=user)


    @app.route('/profile/change-password', methods=['POST'])
    @login_required
    def change_password():
        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        user = g.db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if not check_password_hash(user['password_hash'], current):
            flash('Current password is incorrect.', 'danger')
        elif new_pass != confirm:
            flash('New passwords do not match.', 'danger')
        elif len(new_pass) < 6:
            flash('New password must be at least 6 characters.', 'danger')
        else:
            g.db.execute(
                'UPDATE users SET password_hash = ? WHERE id = ?',
                (generate_password_hash(new_pass), session['user_id'])
            )
            g.db.commit()
            flash('Password changed successfully!', 'success')

        return redirect(url_for('profile'))

    @app.route('/profile/delete-account', methods=['POST'])
    @login_required
    def delete_account():
        user_id = session['user_id']
        user = g.db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if user['username'] == 'admin':
            flash('The administrator account cannot be deleted.', 'danger')
            return redirect(url_for('profile'))

        # Delete related data first (since foreign keys might block deletion)
        # Note: If ON DELETE CASCADE was everywhere, this wouldn't be needed
        g.db.execute('DELETE FROM enrollments WHERE employee_id = ?', (user_id,))
        g.db.execute('DELETE FROM lesson_progress WHERE employee_id = ?', (user_id,))
        g.db.execute('DELETE FROM submissions WHERE employee_id = ?', (user_id,))
        g.db.execute('DELETE FROM attendance WHERE user_id = ?', (user_id,))
        g.db.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
        g.db.execute('DELETE FROM replies WHERE user_id = ?', (user_id,))
        g.db.execute('DELETE FROM learning_insights WHERE user_id = ?', (user_id,))
        
        # If lecturer, also handle courses (this is more complex, might need to reassign or delete?)
        # Let's say for now, we delete their courses too (cascading through lessons, etc.)
        if user['role'] == 'lecturer':
            # This will cascade to lessons, assignments, etc if ON DELETE CASCADE is set
            courses = g.db.execute('SELECT id FROM courses WHERE admin_id = ?', (user_id,)).fetchall()
            for c in courses:
                g.db.execute('DELETE FROM courses WHERE id = ?', (c['id'],))

        # Delete profile picture if exists
        if user['profile_pic_url'] and user['profile_pic_url'].startswith('/uploads/avatar_'):
            pic_path = os.path.join(app.root_path, user['profile_pic_url'].lstrip('/'))
            if os.path.exists(pic_path):
                try: os.remove(pic_path)
                except: pass

        g.db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        g.db.commit()
        
        session.clear()
        flash('Your account has been permanently deleted. We are sorry to see you go!', 'info')
        return redirect(url_for('index'))
