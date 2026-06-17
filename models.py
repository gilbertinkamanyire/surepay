import os
from config import Config
from db_compat import USE_POSTGRES, get_postgres_db, get_sqlite_db

# Track if DB has been initialized this process
_db_initialized = False

def get_db():
    """Get database connection - auto-detects PostgreSQL vs SQLite."""
    if USE_POSTGRES:
        return get_postgres_db()
    else:
        return get_sqlite_db()

def init_db():
    """Initialize database with schema."""
    global _db_initialized
    db = get_db()
    
    if USE_POSTGRES:
        # PostgreSQL schema
        cursor = db._conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                full_name TEXT NOT NULL,
                phone TEXT,
                bio TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                profile_pic_url TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 1,
                current_streak INTEGER DEFAULT 0,
                last_login_date DATE,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS departments (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                admin_id INTEGER NOT NULL REFERENCES users(id),
                department_id INTEGER REFERENCES departments(id),
                category TEXT DEFAULT 'General',
                image_url TEXT DEFAULT '',
                is_published INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                attachment_url TEXT DEFAULT '',
                attachment_type TEXT DEFAULT '',
                order_num INTEGER DEFAULT 1,
                is_hidden INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS enrollments (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                progress REAL DEFAULT 0.0,
                participation_points INTEGER DEFAULT 0,
                last_lesson_id INTEGER DEFAULT NULL,
                UNIQUE(employee_id, course_id)
            );
            
            CREATE TABLE IF NOT EXISTS lesson_progress (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                completed INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                UNIQUE(employee_id, lesson_id)
            );
            
            CREATE TABLE IF NOT EXISTS assessments (
                id SERIAL PRIMARY KEY,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                lesson_id INTEGER REFERENCES lessons(id),
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                questions_json TEXT NOT NULL DEFAULT '[]',
                time_limit INTEGER DEFAULT 0,
                privacy_mode INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                available_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
 
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
                activity_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
 
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS submissions (
                id SERIAL PRIMARY KEY,
                assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                answers_json TEXT NOT NULL DEFAULT '{}',
                score REAL DEFAULT 0,
                max_score REAL DEFAULT 0,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS discussions (
                id SERIAL PRIMARY KEY,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS replies (
                id SERIAL PRIMARY KEY,
                discussion_id INTEGER NOT NULL REFERENCES discussions(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                target_role TEXT DEFAULT 'all',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
 
 
 
            CREATE TABLE IF NOT EXISTS learning_insights (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                course_id INTEGER REFERENCES courses(id),
                insight_type TEXT NOT NULL,
                content TEXT NOT NULL,
                relevance_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
 
            CREATE TABLE IF NOT EXISTS synergy_matches (
                id SERIAL PRIMARY KEY,
                user_a_id INTEGER NOT NULL REFERENCES users(id),
                user_b_id INTEGER NOT NULL REFERENCES users(id),
                course_id INTEGER NOT NULL REFERENCES courses(id),
                match_reason TEXT NOT NULL,
                meeting_link TEXT,
                sync_log TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_id, user_b_id, course_id)
            );

            CREATE TABLE IF NOT EXISTS lesson_qa (
                id SERIAL PRIMARY KEY,
                lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                question TEXT NOT NULL,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
 
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                bandwidth_mode TEXT DEFAULT 'standard',
                theme TEXT DEFAULT 'light'
            );

            CREATE TABLE IF NOT EXISTS badges (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                badge_type TEXT DEFAULT 'completion',
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, course_id, badge_type)
            );

            CREATE TABLE IF NOT EXISTS platform_settings (
                id SERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL DEFAULT ''
            );
        ''')
        
        # Create indexes (ignore if exists)
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_attendance_user ON attendance(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_course ON attendance(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_enrollments_employee ON enrollments(employee_id)",
            "CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_discussions_course ON discussions(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_submissions_employee ON submissions(employee_id)",
            "CREATE INDEX IF NOT EXISTS idx_lesson_progress_employee ON lesson_progress(employee_id)",
        ]
        for idx in indexes:
            try:
                cursor.execute(idx)
            except:
                db._conn.rollback()
        
        db.commit()
        db.close()
    else:
        # SQLite schema (original)
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                full_name TEXT NOT NULL,
                phone TEXT,
                bio TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                profile_pic_url TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 1,
                current_streak INTEGER DEFAULT 0,
                last_login_date TEXT,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                admin_id INTEGER NOT NULL,
                department_id INTEGER,
                category TEXT DEFAULT 'General',
                image_url TEXT DEFAULT '',
                is_published INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id),
                FOREIGN KEY (department_id) REFERENCES departments(id)
            );
            
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                attachment_url TEXT DEFAULT '',
                attachment_type TEXT DEFAULT '',
                order_num INTEGER DEFAULT 1,
                is_hidden INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                progress REAL DEFAULT 0.0,
                participation_points INTEGER DEFAULT 0,
                last_lesson_id INTEGER DEFAULT NULL,
                FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                UNIQUE(employee_id, course_id)
            );
            
            CREATE TABLE IF NOT EXISTS lesson_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                completed INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                UNIQUE(employee_id, lesson_id)
            );
            
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                lesson_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                questions_json TEXT NOT NULL DEFAULT '[]',
                time_limit INTEGER DEFAULT 0,
                privacy_mode INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                available_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            );
 
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                lesson_id INTEGER,
                activity_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
            );
 
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
 
            CREATE INDEX IF NOT EXISTS idx_attendance_user ON attendance(user_id);
            CREATE INDEX IF NOT EXISTS idx_attendance_course ON attendance(course_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
            
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id INTEGER NOT NULL,
                employee_id INTEGER NOT NULL,
                answers_json TEXT NOT NULL DEFAULT '{}',
                score REAL DEFAULT 0,
                max_score REAL DEFAULT 0,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
                FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS discussions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS lesson_qa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                question TEXT NOT NULL,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discussion_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                target_role TEXT DEFAULT 'all',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS learning_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER,
                insight_type TEXT NOT NULL,
                content TEXT NOT NULL,
                relevance_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (course_id) REFERENCES courses(id)
            );
 
            CREATE TABLE IF NOT EXISTS synergy_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a_id INTEGER NOT NULL,
                user_b_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                match_reason TEXT NOT NULL,
                meeting_link TEXT,
                sync_log TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_a_id) REFERENCES users(id),
                FOREIGN KEY (user_b_id) REFERENCES users(id),
                FOREIGN KEY (course_id) REFERENCES courses(id),
                UNIQUE(user_a_id, user_b_id, course_id)
            );
 
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                bandwidth_mode TEXT DEFAULT 'standard',
                theme TEXT DEFAULT 'light',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                badge_type TEXT DEFAULT 'completion',
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                UNIQUE(user_id, course_id, badge_type)
            );

            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL DEFAULT ''
            );
 
            CREATE INDEX IF NOT EXISTS idx_enrollments_employee ON enrollments(employee_id);
            CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
            CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
            CREATE INDEX IF NOT EXISTS idx_discussions_course ON discussions(course_id);
            CREATE INDEX IF NOT EXISTS idx_submissions_employee ON submissions(employee_id);
            CREATE INDEX IF NOT EXISTS idx_lesson_progress_employee ON lesson_progress(employee_id);
        ''')
        
        db.commit()
        db.close()
    
    _db_initialized = True

def seed_db():
    """Seed database with sample data for demonstration."""
    from werkzeug.security import generate_password_hash
    
    db = get_db()
    
    # Check if already seeded
    existing = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if existing > 0:
        db.close()
        return
    
    # Create admin user  (Credentials: admin / admin123)
    db.execute(
        'INSERT INTO users (username, email, password_hash, role, full_name, phone) VALUES (?, ?, ?, ?, ?, ?)',
        ('admin', 'admin@learnug.com', generate_password_hash('admin123'), 'admin', 'System Administrator', '+256700000001')
    )
    
    # Create default business system departments
    for name, desc in [
        ('SIMS', 'Student Information Management System — training for SIMS users'),
        ('CMS', 'Content Management System — training for CMS users'),
        ('PMS', 'Project/Performance Management System — training for PMS users'),
        ('Core Banking', 'Core Banking System — training for banking platform users'),
    ]:
        db.execute('INSERT INTO departments (name, description) VALUES (?, ?)', (name, desc))
    
    db.commit()
    db.close()
    print("Database seeded with admin only!")



if __name__ == '__main__':
    init_db()
    seed_db()
    print("Database initialized and seeded!")
