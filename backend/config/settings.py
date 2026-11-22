"""
Django settings for the Hub Tracker backend.

Secrets are NOT stored in this file. They live in backend/.env, which is
listed in .gitignore so it is never uploaded to GitHub.
Copy .env.example to .env and fill it in (see README.md).
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# BASE_DIR points to the backend folder.
BASE_DIR = Path(__file__).resolve().parent.parent

# Read backend/.env (if it exists) into environment variables.
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY is not set. Copy backend/.env.example to backend/.env '
        'and put a secret key in it (see README.md).'
    )

# True only while developing on your own computer (shows detailed error pages).
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')


# Applications
INSTALLED_APPS = [
    # Django built-in apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party packages
    'rest_framework',
    'corsheaders',

    # Our apps
    'core',
    'shipments',
    'reports',
]

MIDDLEWARE = [
    # CorsMiddleware must come before CommonMiddleware.
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'core.security_log.SecurityLogMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database: SQLite file inside the backend folder.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE', 'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;'},
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# A second folder for backups, OFF this laptop's own disk: for example your
# Google Drive folder, so every backup is also uploaded automatically.
# Set it in .env:  BACKUP_COPY_DIR=G:\My Drive\Hub Tracker backups
# Leave it out to keep backups only in backend/backups.
BACKUP_COPY_DIR = os.environ.get('BACKUP_COPY_DIR', '').strip()

# Tests only: a fast password hasher. The real one is slow on purpose (to make
# stolen passwords hard to crack), which made the test run take 15+ minutes.
# Your real login is NOT affected: this only applies to "manage.py test".
# Tests also never copy backups into your real second folder.
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    BACKUP_COPY_DIR = ''


# Language and time: Nigeria (WAT, UTC+1).
# This matters because reports are grouped by date.
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# CORS: allow the React dev server (Vite runs on port 5173) to call this API.
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]

# CSRF: trust changes (login, status updates...) sent from the React page.
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]


# Log out after this many minutes without activity. Every request to Django
# restarts the clock, so you are only logged out when you really stop using it.
# The website reads this number from /api/auth/me/ and logs out at the same time.
IDLE_TIMEOUT_MINUTES = 15
SESSION_COOKIE_AGE = IDLE_TIMEOUT_MINUTES * 60
SESSION_SAVE_EVERY_REQUEST = True; SESSION_COOKIE_SAMESITE = 'Strict'; CSRF_COOKIE_SAMESITE = 'Strict'  # other websites can't use your login, even through a link

# Wrong passwords: after this many failed logins for one username, login is
# locked for that username for LOGIN_LOCKOUT_MINUTES. A correct login resets it.
# A shipment with this many failed delivery attempts ("Delivery Unsuccessful")
# is flagged as ready to initiate a return. Change the number to adjust it.
RETURN_AFTER_ATTEMPTS = 3

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 5; AUTHENTICATION_BACKENDS = ['core.login_lock.LockoutBackend']  # the lock covers every login page

# Security log: backend/logs/security.log (see core/security_log.py).
# 1 MB per file, the 5 newest old files kept (security.log.1 ... .5).
# Django's own security warnings (e.g. a forged Host header) go there too.
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {'one_line': {'()': 'core.security_log.OneLine'}},
    'formatters': {
        'security': {'format': '%(asctime)s  %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S'},
    },
    'handlers': {
        'security_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'security.log',
            'maxBytes': 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'delay': True,  # only opened when something is written
            'formatter': 'security',
            'filters': ['one_line'],
        },
    },
    'loggers': {
        'hub.security': {'handlers': ['security_file'], 'level': 'INFO', 'propagate': False},
        'django.security': {'handlers': ['security_file'], 'level': 'WARNING', 'propagate': False},
    },
}
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    LOGGING['handlers']['security_file'] = {'class': 'logging.NullHandler'}  # tests never write the real log

# Django REST Framework
REST_FRAMEWORK = {
    # You must be logged in to use the API (log in through /admin or /api-auth/login).
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Lists come back 50 rows at a time: ?page=2 for the next 50.
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    # Turns our services' ValidationErrors into clean 400 responses.
    'EXCEPTION_HANDLER': 'core.exceptions.api_exception_handler',
}