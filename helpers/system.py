from flask import g, session
from models import get_db
from db_compat import USE_POSTGRES

TRANSLATIONS = {
    'en': {
        'How It Works': 'How It Works',
        'About': 'About',
        'Support': 'Support',
        'Home': 'Home',
        'Dashboard': 'Dashboard',
        'Learning': 'Learning',
        'Share': 'Share',
        'Low Data Mode Enabled': 'Low Data Mode Enabled',
        'Offline support active': 'Offline support active',
        'Student': 'Student',
        'Lecturer': 'Lecturer',
        'Course Lessons': 'Course Lessons',
        'Quiz Required': 'Quiz Required',
        'Quiz Completed': 'Quiz Completed',
        'Mark as Complete': 'Mark as Complete',
        'Take Questionnaire': 'Take Questionnaire',
        'Progress': 'Progress',
        'Participants': 'Participants'
    },
    'lg': {
        'How It Works': 'Enkola Entuufu',
        'About': 'Ku Byo',
        'Support': 'Obuwandiike',
        'Home': 'Wankoko',
        'Dashboard': 'Ekibuga',
        'Learning': 'Okwongera Omuwendo',
        'Share': 'Gula',
        'Low Data Mode Enabled': 'Ekikola ekya Ddata Emitono kikolebwa',
        'Offline support active': 'Okuyamba nga tolina intaneti kukola',
        'Student': 'Muwandiisi',
        'Lecturer': 'Omuyigirizi',
        'Course Lessons': 'Ebikozesebwa by Amakubo',
        'Quiz Required': 'Ekibuuzo kitwaliddwa',
        'Quiz Completed': 'Oluvioolu lussibweddemu',
        'Mark as Complete': 'Laga nga kikende',
        'Take Questionnaire': 'Wangula Ebibuuzo',
        'Progress': 'Okukyusa',
        'Participants': 'Abategeeza'
    },
    'sw': {
        'How It Works': 'Jinsi Inavyofanya Kazi',
        'About': 'Kuhusu',
        'Support': 'Msaada',
        'Home': 'Nyumbani',
        'Dashboard': 'Dashibodi',
        'Learning': 'Kujifunza',
        'Share': 'Shiriki',
        'Low Data Mode Enabled': 'Hali ya Data Chini Imezimwa',
        'Offline support active': 'Msaada wa nje ya mtandao unafanya kazi',
        'Student': 'Mwanafunzi',
        'Lecturer': 'Mwalimu',
        'Course Lessons': 'Masomo ya Kozi',
        'Quiz Required': 'Mtihani Unahitajika',
        'Quiz Completed': 'Mtihani Umefanyika',
        'Mark as Complete': 'Wezesha Kukamilisha',
        'Take Questionnaire': 'Chukua Dodoso',
        'Progress': 'Maendeleo',
        'Participants': 'Washiriki',
        'Synergy Connect': 'Muunganisho wa Harambee',
        'Cognitive Mirror': 'Kioo cha Utambuzi',
        'Back to Course': 'Rudi kwenye Kozi',
        'Search': 'Tafuta',
        'Profile': 'Wasifu',
        'Settings': 'Mipangilio',
        'Logout': 'Ondoka'
    }
}

def setup_helpers(app):
    @app.before_request
    def before_request():
        g.db = get_db()
        
        from flask import request, redirect, url_for, flash
        # Completely lock down the system, only allowing login, register, and the landing page for unauthenticated users.
        allowed_endpoints = [
            'login', 'register', 'forgot_password', 'index',
            'static', 'serve_uploads', 'manifest', 'sw',
            'toggle_theme', 'toggle_bandwidth', 'toggle_language'
        ]
        
        # If the endpoint requires authorization and the user is not signed in
        if request.endpoint and request.endpoint not in allowed_endpoints and not request.endpoint.startswith('static'):
            if 'user_id' not in session:
                flash("🔒 Please sign in to access the system.", "danger")
                return redirect(url_for('login', next=request.url))

        # Terms-of-service gate: signed-in users must accept the current terms
        # version before they can use the rest of the platform (enforced on
        # first login and again whenever an admin updates the terms).
        if 'user_id' in session:
            terms_exempt = [
                'accept_terms', 'logout', 'terms', 'privacy',
                'static', 'serve_uploads', 'manifest', 'sw',
                'toggle_theme', 'toggle_bandwidth', 'toggle_language',
            ]
            if request.endpoint and request.endpoint not in terms_exempt and not request.endpoint.startswith('static'):
                try:
                    version_row = g.db.execute(
                        "SELECT value FROM platform_settings WHERE key = 'terms_version'"
                    ).fetchone()
                    current_version = version_row['value'] if version_row and version_row['value'] else '1'
                    user_row = g.db.execute(
                        'SELECT terms_version_accepted FROM users WHERE id = ?',
                        (session['user_id'],)
                    ).fetchone()
                    accepted_version = user_row['terms_version_accepted'] if user_row else None
                    if str(accepted_version) != str(current_version):
                        return redirect(url_for('accept_terms'))
                except Exception:
                    pass

    @app.teardown_appcontext
    def close_db(exception):
        db = getattr(g, 'db', None)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    def translate(text):
        lang = session.get('language', 'en')
        if lang in TRANSLATIONS and text in TRANSLATIONS[lang]:
            return TRANSLATIONS[lang][text]
        return text

    @app.context_processor
    def inject_user():
        user = None
        try:
            if 'user_id' in session:
                user = g.db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        except Exception:
            pass
        return {
            'current_user': user,
            '_': translate,
            'current_lang': session.get('language', 'en')
        }
