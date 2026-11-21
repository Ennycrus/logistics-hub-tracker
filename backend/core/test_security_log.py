"""
Tests for the security log (core/security_log.py).

Run with:  python manage.py test core.test_security_log
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

GOOD = 'a-good-password-123'


@override_settings(LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCKOUT_MINUTES=5)
class SecurityLogTests(TestCase):

    def setUp(self):
        cache.clear()
        User.objects.create_superuser('dammy', password=GOOD)
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def logged(self, action):
        """Run action() and return the security log lines it wrote."""
        with self.assertLogs('hub.security', 'INFO') as captured:
            action()
        return [record.getMessage() for record in captured.records]

    def login(self, password, username='dammy'):
        return self.client.post('/api/auth/login/', {'username': username, 'password': password},
                                format='json', HTTP_USER_AGENT='TestBrowser/1.0')

    def test_good_login(self):
        lines = self.logged(lambda: self.login(GOOD))
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('LOGIN_OK  '))
        self.assertIn('user="dammy"', lines[0])
        self.assertIn('ip=127.0.0.1', lines[0])
        self.assertIn('browser="TestBrowser/1.0"', lines[0])

    def test_wrong_password_never_logs_the_password(self):
        lines = self.logged(lambda: self.login('my-secret-guess'))
        self.assertTrue(lines[0].startswith('LOGIN_FAILED'))
        self.assertNotIn('my-secret-guess', ' '.join(lines))

    def test_lock_and_blocked_attempts(self):
        for _ in range(4):
            self.login('wrong')
        self.assertEqual([line.split()[0] for line in self.logged(lambda: self.login('wrong'))],
                         ['LOGIN_FAILED', 'ACCOUNT_LOCKED'])
        self.assertTrue(self.logged(lambda: self.login(GOOD))[0].startswith('LOGIN_BLOCKED'))

    def test_admin_login_is_logged_too(self):
        lines = self.logged(lambda: Client().post('/admin/login/', {'username': 'dammy', 'password': 'x'}))
        self.assertTrue(lines[0].startswith('LOGIN_FAILED'))

    def test_log_injection_is_impossible(self):
        fake = 'evil\n2026-01-01 00:00:00  LOGIN_OK  user="dammy"'
        lines = self.logged(lambda: self.login('x', username=fake))
        for line in lines:
            self.assertNotIn('\n', line)
            self.assertNotIn('"dammy"', line)  # the quotes were neutralised too

    def test_password_change_events(self):
        self.login(GOOD)
        change = lambda current: self.client.post(  # noqa: E731
            '/api/auth/change-password/', {'current_password': current, 'new_password': 'Hub-Tracker-2026-new'},
            format='json')
        self.assertTrue(self.logged(lambda: change('guess'))[0].startswith('PASSWORD_CHANGE_FAILED'))
        lines = self.logged(lambda: change(GOOD))
        self.assertTrue(lines[0].startswith('PASSWORD_CHANGED'))
        self.assertNotIn('Hub-Tracker-2026-new', ' '.join(lines))

    def test_logout(self):
        self.login(GOOD)
        self.assertTrue(self.logged(lambda: self.client.post('/api/auth/logout/'))[0].startswith('LOGOUT'))

    def test_api_without_login(self):
        lines = self.logged(lambda: APIClient().get('/api/shipments/'))
        self.assertTrue(lines[0].startswith('ACCESS_DENIED'))
        self.assertIn('path="/api/shipments/"', lines[0])
        self.assertIn('status=403', lines[0])

    def test_looking_for_hidden_pages(self):
        self.client.force_authenticate(User.objects.get(username='dammy'))
        lines = self.logged(lambda: self.client.get('/api/secret-backup/'))
        self.assertTrue(lines[0].startswith('NOT_FOUND'))

    def test_refused_upload(self):
        self.client.force_authenticate(User.objects.get(username='dammy'))
        upload = SimpleUploadedFile('virus.exe', b'MZ...')
        lines = self.logged(lambda: self.client.post('/api/imports/preview/', {'file': upload}, format='multipart'))
        self.assertTrue(lines[0].startswith('UPLOAD_REFUSED'))
        self.assertIn('file="virus.exe"', lines[0])
        self.assertIn('Excel', lines[0])  # the reason

    def test_normal_work_is_not_logged(self):
        self.client.force_authenticate(User.objects.get(username='dammy'))
        with self.assertNoLogs('hub.security'):
            self.client.get('/api/shipments/')

    def test_forged_host_header_goes_to_the_log(self):
        with self.assertLogs('django.security', 'WARNING'):
            Client().get('/api/auth/me/', HTTP_HOST='evil.example.com')