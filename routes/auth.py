import secrets
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import login_required, role_required, send_notification_email, send_reset_email

def register_auth(app):


    @app.route('/')
    def index():
        # Get stats for landing page
        stats = {
            'categories': g.db.execute('SELECT COUNT(*) FROM categories WHERE is_published = 1').fetchone()[0],
            'students': g.db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0],
            'lecturers': g.db.execute("SELECT COUNT(*) FROM users WHERE role = 'lecturer'").fetchone()[0],
        }

        # Get featured categories
        featured = g.db.execute('''
            SELECT c.*, u.full_name as admin_name,
                   (SELECT COUNT(*) FROM enrollments WHERE category_id = c.id) as student_count,
                   (SELECT COUNT(*) FROM lessons WHERE category_id = c.id) as lesson_count
            FROM categories c JOIN users u ON c.admin_id = u.id
            WHERE c.is_published = 1
            ORDER BY c.created_at DESC LIMIT 6
        ''').fetchall()

        return render_template('index.html', stats=stats, featured=featured)


    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')

            user = g.db.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)',
                               (username, username)).fetchone()

            if user and check_password_hash(user['password_hash'], password):
                if not user['is_active']:
                    flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                    return redirect(url_for('login'))

                # Specific check for lecturers whose accounts are still pending admin approval
                if user['role'] == 'lecturer' and not user['is_verified']:
                    flash('Welcome, your lecturer account is currently pending administrative verification. Please wait for an email confirmation or contact admin.', 'warning')
                    return redirect(url_for('login'))

                session.permanent = True
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['full_name'] = user['full_name']
                
                from datetime import date, datetime
                today = date.today()
                try:
                    last_login_str = user['last_login_date']
                except (IndexError, KeyError):
                    last_login_str = None
                try:
                    current_streak = user['current_streak'] or 0
                except (IndexError, KeyError):
                    current_streak = 0
                
                if last_login_str:
                    try:
                        last_login = datetime.strptime(last_login_str, '%Y-%m-%d').date()
                        delta = (today - last_login).days
                        if delta == 1:
                            current_streak += 1
                        elif delta > 1:
                            current_streak = 1
                    except Exception:
                        current_streak = 1
                else:
                    current_streak = 1
                
                g.db.execute('UPDATE users SET last_login_date = ?, current_streak = ? WHERE id = ?', 
                             (today.strftime('%Y-%m-%d'), current_streak, user['id']))
                g.db.commit()

                if current_streak > 1:
                    flash(f'Welcome back, {user["full_name"]}! You are on a {current_streak}-day streak! 🔥', 'success')
                else:
                    flash(f'Welcome back, {user["full_name"]}!', 'success')
                
                # Check for redirections (standard next param)
                next_url = request.args.get('next')
                if not next_url or not next_url.startswith('/'):
                    # Ensure it's a relative URL or starts with our domain to prevent open redirect vulnerabilities
                    next_url = url_for('dashboard')
                
                resp = make_response(redirect(next_url))
                resp.set_cookie('saved_username', user['username'], max_age=30*24*60*60)
                return resp
            else:
                flash('Invalid username/email or password. Please try again.', 'danger')

        saved_username = request.cookies.get('saved_username', '')
        return render_template('auth/login.html', saved_username=saved_username)


    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            flash('Self-registration is currently disabled. Please contact the administrator to create an account.', 'danger')
            return redirect(url_for('register'))

        return render_template('auth/register.html')


    @app.route('/accept-terms', methods=['GET', 'POST'])
    def accept_terms():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        # Load current terms content + version
        rows = g.db.execute("SELECT key, value FROM platform_settings WHERE key IN ('terms_content', 'terms_version')").fetchall()
        settings = {r['key']: r['value'] for r in rows}
        terms_content = settings.get('terms_content', '')
        terms_version = settings.get('terms_version', '1')

        if request.method == 'POST':
            if request.form.get('accept'):
                g.db.execute(
                    'UPDATE users SET terms_accepted = 1, terms_version_accepted = ? WHERE id = ?',
                    (terms_version, session['user_id'])
                )
                g.db.commit()
                flash('Thank you for accepting the Terms & Conditions.', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('You must tick the box to accept the Terms & Conditions before continuing.', 'warning')

        return render_template('auth/accept_terms.html',
                               terms_content=terms_content,
                               terms_version=terms_version)


    @app.route('/logout')
    def logout():
        # Preserve user preferences (theme and bandwidth) but remove auth
        theme = session.get('theme_mode')
        bandwidth = session.get('bandwidth_mode')
        
        session.clear()
        
        # Restore preferences so the screen doesn't suddenly flash white/full bandwidth
        if theme:
            session['theme_mode'] = theme
        if bandwidth:
            session['bandwidth_mode'] = bandwidth
            
        flash('You have been logged out.', 'info')
        return redirect(url_for('index'))


    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
            
        if request.method == 'POST':
            email = request.form.get('email', '').strip()
            if email:
                user = g.db.execute('SELECT id, full_name, email FROM users WHERE email = ?', (email,)).fetchone()
                if user:
                    token = secrets.token_urlsafe(32)
                    expiry = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # simplistic expiry, could be +1 hour
                    # In a real app we'd set an actual expiry time, for now let's just store the token
                    g.db.execute('UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?',
                               (token, expiry, user['id']))
                    g.db.commit()
                    
                    reset_link = url_for('reset_password', token=token, _external=True)
                    send_reset_email(user['email'], user['full_name'], reset_link)

                flash('If an account exists with that email, a password reset link has been sent.', 'info')
                return redirect(url_for('login'))
        return render_template('auth/forgot_password.html')

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
            
        user = g.db.execute('SELECT id, username FROM users WHERE reset_token = ?', (token,)).fetchone()
        if not user:
            flash('Invalid or expired reset token.', 'danger')
            return redirect(url_for('forgot_password'))
            
        if request.method == 'POST':
            new_pass = request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')
            
            if len(new_pass) < 6:
                flash('Password must be at least 6 characters.', 'danger')
            elif new_pass != confirm:
                flash('Passwords do not match.', 'danger')
            else:
                g.db.execute('UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?',
                           (generate_password_hash(new_pass), user['id']))
                g.db.commit()
                flash('Your password has been reset. You can now log in.', 'success')
                return redirect(url_for('login'))
                
        return render_template('auth/reset_password.html', token=token)

