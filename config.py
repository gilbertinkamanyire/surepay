import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'SurePay-2026-platform-secret-key')
    
    # On Render, try persistent /data directory first, fall back to /tmp
    if os.environ.get('RENDER'):
        _data_dir = '/data'
        # Check if /data exists and is writable (persistent disk attached)
        try:
            os.makedirs(_data_dir, exist_ok=True)
            # Test if we can actually write to it
            _test_file = os.path.join(_data_dir, '.write_test')
            with open(_test_file, 'w') as f:
                f.write('ok')
            os.remove(_test_file)
            DATABASE = os.path.join(_data_dir, 'database.db')
            UPLOAD_FOLDER = os.path.join(_data_dir, 'uploads')
        except (OSError, PermissionError):
            # No persistent disk — use /tmp (data resets on redeploy)
            DATABASE = '/tmp/database.db'
            UPLOAD_FOLDER = '/tmp/uploads'
        # Ensure upload folder exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # On Vercel, the filesystem is read-only except for /tmp
    elif os.environ.get('VERCEL'):
        DATABASE = '/tmp/database.db'
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        DATABASE = os.path.join(BASE_DIR, 'database.db')
        UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
        
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload
    ITEMS_PER_PAGE = 10
    
    # OpenAI Config
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'your-openai-api-key-here')

    # Mailjet Config
    MAILJET_API_KEY = os.environ.get('MAILJET_API_KEY', 'd44fbbd7724c453cb6eb707c803beae6')
    MAILJET_API_SECRET = os.environ.get('MAILJET_API_SECRET', 'e0a275bf5d41b9aab19970466be8f148')
    MAILJET_SENDER_EMAIL = os.environ.get('MAILJET_SENDER_EMAIL', 'okiria.vincent@student.utamu.ac.ug')

