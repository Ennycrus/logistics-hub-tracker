"""
The security log: one line for every security-relevant event, written to
backend/logs/security.log (set up in settings.LOGGING).

    2026-11-21 14:40:02  LOGIN_FAILED  user="dammy" ip=192.168.56.101 browser="python-requests/2.32"

Events:
  LOGIN_OK                 a correct username and password (any login page)
  LOGIN_FAILED             a wrong username or password
  ACCOUNT_LOCKED           the wrong password that locked the username
  LOGIN_BLOCKED            a login tried while the username is locked
  LOGOUT                   logged out from the website
  PASSWORD_CHANGED         password changed in Settings
  PASSWORD_CHANGE_FAILED   wrong current password on Change password
  PASSWORD_CHANGE_BLOCKED  Change password tried while locked
  ACCESS_DENIED            a 401/403 answer: not logged in, CSRF check failed...
  NOT_FOUND                a 404 under /api/ or /admin/ (someone looking for pages)
  UPLOAD_REFUSED           an import or stock-count file was refused, and why
  SUSPICIOUS               Django's own security warnings, e.g. a forged Host header

Rules:
  - NEVER a password or the CSRF token. Only who, from where, what and when.
  - Everything that comes from outside (username, browser, path, reasons) is
    cleaned first: no new lines, no control characters, no quotes, and a length
    limit. Otherwise an attacker could type a username containing a new line
    and write a fake line into the log ("log injection").
  - Normal work (opening reports, updating shipments) is NOT logged, so real
    attacks are not buried.

Watch it live in PowerShell:   Get-Content backend\\logs\\security.log -Wait -Tail 20
"""

import logging
import re

logger = logging.getLogger('hub.security')

UNSAFE = re.compile(r'[\x00-\x1f\x7f"\\]')  # control characters (incl. new lines), quotes, backslashes
QUOTED = {'user', 'browser', 'path', 'reason', 'file'}


def clean(value, limit=120):
    text = UNSAFE.sub('?', str(value))
    return text if len(text) <= limit else text[:limit] + '...'


def client_ip(request):
    # REMOTE_ADDR is the real connection; headers such as X-Forwarded-For are
    # typed by the client and could be faked, so they are not trusted here.
    return clean(request.META.get('REMOTE_ADDR', '-'), 45)


def log_event(event, request=None, **fields):
    parts = [event]
    if request is not None:
        fields.setdefault('ip', client_ip(request))
        fields.setdefault('browser', request.META.get('HTTP_USER_AGENT', '-'))
    for key, value in fields.items():
        value = clean(value, 200 if key in ('path', 'reason') else 120)
        parts.append(f'{key}="{value}"' if key in QUOTED else f'{key}={value}')
    logger.info('  '.join([parts[0], ' '.join(parts[1:])]).rstrip())


class OneLine(logging.Filter):
    """
    Turns Django's own security warnings (e.g. a forged Host header) into one
    clean SUSPICIOUS line like ours: no traceback, and the attacker's text cleaned.
    """

    def filter(self, record):
        if record.name.startswith('django.security'):
            request = getattr(record, 'request', None)
            ip = client_ip(request) if request is not None else '-'
            kind = record.name.rsplit('.', 1)[-1]
            record.msg = f'SUSPICIOUS  kind={clean(kind, 40)} ip={ip} reason="{clean(record.getMessage(), 200)}"'
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


UPLOAD_PATHS = {'/api/imports/preview/', '/api/imports/confirm/', '/api/stock-count/'}


class SecurityLogMiddleware:
    """Logs refused requests: 401/403 anywhere, 404 under /api/ and /admin/, refused uploads."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        code = response.status_code
        path = request.path
        user = request.user.get_username() if getattr(request, 'user', None) and request.user.is_authenticated else '-'

        if code in (401, 403):
            log_event('ACCESS_DENIED', request, user=user, method=request.method, path=path,
                      status=code, reason=self.reason(response))
        elif code == 404 and path.startswith(('/api/', '/admin/')):
            log_event('NOT_FOUND', request, user=user, method=request.method, path=path)
        elif code == 400 and request.method == 'POST' and path in UPLOAD_PATHS:
            upload = request.FILES.get('file')
            log_event('UPLOAD_REFUSED', request, user=user, path=path,
                      file=upload.name if upload else '-', reason=self.reason(response))
        return response

    @staticmethod
    def reason(response):
        data = getattr(response, 'data', None)
        if isinstance(data, dict):
            return data.get('error') or data.get('detail') or '-'
        return '-'