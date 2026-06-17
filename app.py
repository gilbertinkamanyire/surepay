import os
from flask import Flask, redirect, request, session, url_for
from werkzeug.security import generate_password_hash
from config import Config
from models import init_db, seed_db, get_db
from helpers import setup_helpers, register_filters
from db_compat import USE_POSTGRES

from routes.auth import register_auth
from routes.dashboard import register_dashboard
from routes.courses import register_courses
from routes.departments import register_departments
from routes.lessons import register_lessons
from routes.assessments import register_assessments
from routes.discussions import register_discussions

from routes.grades import register_grades
from routes.profile import register_profile
from routes.admin import register_admin
from routes.pages import register_pages
from routes.errors import register_errors
from routes.serviceworker import register_serviceworker
from routes.unique import register_unique

app = Flask(__name__)
app.config.from_object(Config)


# ---------------------------------------------------------------------------
# Simple toggle routes (theme, bandwidth, language)
# ---------------------------------------------------------------------------

@app.route('/toggle-theme', methods=['POST'])
def toggle_theme():
    current_mode = session.get('theme_mode', 'light')
    new_mode = 'dark' if current_mode == 'light' else 'light'
    session['theme_mode'] = new_mode

    if 'user_id' in session:
        db = get_db()
        try:
            if USE_POSTGRES:
                db.execute(
                    'INSERT INTO user_preferences (user_id, theme) VALUES (%s, %s) '
                    'ON CONFLICT (user_id) DO UPDATE SET theme = EXCLUDED.theme',
                    (session['user_id'], new_mode)
                )
            else:
                db.execute(
                    'INSERT OR REPLACE INTO user_preferences (user_id, theme) VALUES (?, ?)',
                    (session['user_id'], new_mode)
                )
            db.commit()
        finally:
            db.close()

    return redirect(request.referrer or url_for('index'))


@app.route('/toggle-bandwidth', methods=['POST'])
def toggle_bandwidth():
    mode = request.form.get('mode', 'standard')
    session['bandwidth_mode'] = mode

    if 'user_id' in session:
        db = get_db()
        try:
            if USE_POSTGRES:
                db.execute(
                    'INSERT INTO user_preferences (user_id, bandwidth_mode) VALUES (%s, %s) '
                    'ON CONFLICT (user_id) DO UPDATE SET bandwidth_mode = EXCLUDED.bandwidth_mode',
                    (session['user_id'], mode)
                )
            else:
                db.execute(
                    'INSERT OR REPLACE INTO user_preferences (user_id, bandwidth_mode) VALUES (?, ?)',
                    (session['user_id'], mode)
                )
            db.commit()
        finally:
            db.close()

    return redirect(request.referrer or url_for('index'))


@app.route('/toggle-language', methods=['POST'])
def toggle_language():
    import urllib.parse
    from flask import make_response
    language = request.form.get('language', 'en')
    session['language'] = language
    
    resp = make_response(redirect(request.referrer or url_for('index')))
    
    if language == 'en':
        resp.delete_cookie('googtrans', path='/')
    else:
        resp.set_cookie('googtrans', f'/en/{language}', path='/')
        
    return resp

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------

if USE_POSTGRES:
    try:
        init_db()
        seed_db()
    except Exception as e:
        print(f"DB init note: {e}")
else:
    if not os.path.exists(Config.DATABASE):
        init_db()
        seed_db()

# Auto-fix: ensure admin account exists with known credentials on every start
try:
    db_fix = get_db()
    admin_hash = generate_password_hash('admin123')
    admin_email = 'admin@SurePay.com'
    admin_username = 'admin'
    admin_full_name = 'System Administrator'
    admin_phone = '+256700000001'

    if USE_POSTGRES:
        existing_admin = db_fix.execute(
            "SELECT id FROM users WHERE username = %s", (admin_username,)
        ).fetchone()
        if existing_admin:
            db_fix.execute(
                "UPDATE users SET email = %s, password_hash = %s WHERE username = %s",
                (admin_email, admin_hash, admin_username)
            )
        else:
            db_fix.execute(
                "INSERT INTO users (username, email, password_hash, role, full_name, phone, is_active, is_verified) "
                "VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)",
                (admin_username, admin_email, admin_hash, 'admin', admin_full_name, admin_phone)
            )
    else:
        existing_admin = db_fix.execute(
            "SELECT id FROM users WHERE username = ?", (admin_username,)
        ).fetchone()
        if existing_admin:
            db_fix.execute(
                "UPDATE users SET email = ?, password_hash = ? WHERE username = ?",
                (admin_email, admin_hash, admin_username)
            )
        else:
            db_fix.execute(
                "INSERT INTO users (username, email, password_hash, role, full_name, phone, is_active, is_verified) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, 1)",
                (admin_username, admin_email, admin_hash, 'admin', admin_full_name, admin_phone)
            )

    # Also run the available_until migration for existing databases
    try:
        if USE_POSTGRES:
            db_fix.execute("ALTER TABLE assessments ADD COLUMN IF NOT EXISTS available_until TEXT")
        else:
            db_fix.execute("ALTER TABLE assessments ADD COLUMN available_until TEXT")
    except Exception:
        pass  # Column already exists

    # Migration: create badges table if it doesn't exist
    try:
        if USE_POSTGRES:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS badges (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    badge_type TEXT DEFAULT 'completion',
                    awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, course_id, badge_type)
                )
            ''')
        else:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS badges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    badge_type TEXT DEFAULT 'completion',
                    awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                    UNIQUE(user_id, course_id, badge_type)
                )
            ''')
    except Exception:
        pass

    # Migration: create platform_settings table if it doesn't exist
    try:
        if USE_POSTGRES:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS platform_settings (
                    id SERIAL PRIMARY KEY,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL DEFAULT ''
                )
            ''')
        else:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS platform_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL DEFAULT ''
                )
            ''')
    except Exception:
        pass

    # Migration: role restructuring to corporate
    try:
        db_fix.execute("UPDATE users SET role='employee' WHERE role='student'")
        db_fix.execute("UPDATE users SET role='admin' WHERE role='lecturer'")
    except Exception:
        pass

    try:
        db_fix.execute("ALTER TABLE courses RENAME COLUMN lecturer_id TO admin_id")
    except Exception:
        pass
        
    try:
        db_fix.execute("ALTER TABLE enrollments RENAME COLUMN student_id TO employee_id")
        db_fix.execute("ALTER TABLE lesson_progress RENAME COLUMN student_id TO employee_id")
        db_fix.execute("ALTER TABLE submissions RENAME COLUMN student_id TO employee_id")
    except Exception:
        pass

    # Migration: create bookmarks table for employee bookmarks
    try:
        if USE_POSTGRES:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    course_id INTEGER,
                    lesson_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        else:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER,
                    lesson_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
    except Exception:
        pass

    # Migration: create personal_notes table for employee private notes on lessons
    try:
        if USE_POSTGRES:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS personal_notes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    content TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        else:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS personal_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    lesson_id INTEGER NOT NULL,
                    content TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
                )
            ''')
    except Exception:
        pass

    # Migration: streak tracking on users
    for ddl in (
        "ALTER TABLE users ADD COLUMN current_streak INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_login_date TEXT",
    ):
        try:
            db_fix.execute(ddl)
        except Exception:
            pass  # Column already exists

    # Migration: lesson_qa table
    try:
        if USE_POSTGRES:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS lesson_qa (
                    id SERIAL PRIMARY KEY,
                    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    question TEXT NOT NULL,
                    answer TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        else:
            db_fix.execute('''
                CREATE TABLE IF NOT EXISTS lesson_qa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
    except Exception:
        pass

    # Migration: terms-of-service acceptance tracking on users
    for ddl in (
        "ALTER TABLE users ADD COLUMN terms_accepted INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN terms_version_accepted TEXT",
    ):
        try:
            db_fix.execute(ddl)
        except Exception:
            pass  # Column already exists

    # Seed default terms content + version if not already configured
    try:
        existing_terms = db_fix.execute(
            "SELECT key FROM platform_settings WHERE key = 'terms_content'"
        ).fetchone()
        if not existing_terms:
            default_terms = (
                "Welcome to SurePay.\n\n"
                "By creating an account and using this platform you agree to the following terms:\n\n"
                "1. You will use the platform for legitimate learning and training purposes only.\n"
                "2. You are responsible for keeping your login credentials secure.\n"
                "3. Course content and materials are provided for your personal development and "
                "may not be redistributed without permission.\n"
                "4. You agree to engage respectfully with other learners and staff.\n"
                "5. SurePay may update these terms from time to time; continued use after an update "
                "means you accept the revised terms.\n\n"
                "If you do not agree with these terms, please do not use the platform."
            )
            placeholder = '%s' if USE_POSTGRES else '?'
            db_fix.execute(
                f"INSERT INTO platform_settings (key, value) VALUES ({placeholder}, {placeholder})",
                ('terms_content', default_terms),
            )
            db_fix.execute(
                f"INSERT INTO platform_settings (key, value) VALUES ({placeholder}, {placeholder})",
                ('terms_version', '1'),
            )
    except Exception:
        pass

    db_fix.commit()
    db_fix.close()
except Exception as e:
    print(f"Data fix skipped: {e}")


# ---------------------------------------------------------------------------
# Context processor — inject nav departments + current user
# ---------------------------------------------------------------------------

@app.context_processor
def inject_nav_data():
    try:
        db = get_db()
        depts = db.execute('SELECT id, name, description FROM departments ORDER BY name').fetchall()
        # Load platform branding settings
        settings_rows = db.execute('SELECT key, value FROM platform_settings').fetchall()
        db.close()
        platform = {row['key']: row['value'] for row in settings_rows}
        # Provide defaults (brand from assets: deep blue primary, vivid green accent)
        platform.setdefault('company_name', 'SurePay')
        platform.setdefault('primary_color', '#312783')  # Deep brand blue (dominant)
        platform.setdefault('secondary_color', '#95c01f')  # Vivid brand green (accent)
        platform.setdefault('logo_url', '')
        platform.setdefault('terms_content', '')
        platform.setdefault('terms_version', '1')
        return dict(nav_departments=depts, platform=platform)
    except Exception:
        return dict(nav_departments=[], platform={
            'company_name': 'SurePay',
            'primary_color': '#312783',
            'secondary_color': '#95c01f',
            'logo_url': '',
            'terms_content': '',
            'terms_version': '1'
        })


# ---------------------------------------------------------------------------
# Ensure upload directory exists & register helpers / blueprints
# ---------------------------------------------------------------------------

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

setup_helpers(app)
register_filters(app)

register_auth(app)
register_dashboard(app)
register_courses(app)
register_departments(app)
register_lessons(app)
register_assessments(app)
register_discussions(app)

register_grades(app)
register_profile(app)
register_admin(app)
register_pages(app)
register_errors(app)
register_serviceworker(app)
register_unique(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
