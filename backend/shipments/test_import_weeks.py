"""
Tests for the import history by week (GET /api/imports/?week=<date>).

Run with:  python manage.py test shipments.test_import_weeks
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import ImportBatch


def batch(name, date):
    return ImportBatch.objects.create(
        file_name=name, file_hash=name, reporting_date=date, column_index=0, total_rows=1,
    )


class ImportHistoryByWeekTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        batch('last-sunday.xlsx', datetime.date(2026, 11, 15))
        batch('monday.xlsx', datetime.date(2026, 11, 16))
        batch('friday.xlsx', datetime.date(2026, 11, 20))
        batch('sunday.xlsx', datetime.date(2026, 11, 22))
        batch('next-monday.xlsx', datetime.date(2026, 11, 23))

    def names(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return [b['file_name'] for b in response.json()['results']]

    def test_only_that_weeks_imports_newest_day_first(self):
        self.assertEqual(self.names('/api/imports/?week=2026-11-18'),
                         ['sunday.xlsx', 'friday.xlsx', 'monday.xlsx'])

    def test_any_day_of_the_week_gives_the_same_week(self):
        self.assertEqual(self.names('/api/imports/?week=2026-11-16'), self.names('/api/imports/?week=2026-11-22'))

    def test_empty_week(self):
        self.assertEqual(self.names('/api/imports/?week=2026-10-01'), [])

    def test_without_week_everything_is_listed(self):
        self.assertEqual(len(self.names('/api/imports/')), 5)

    def test_bad_week_is_refused(self):
        self.assertEqual(self.client.get('/api/imports/?week=soon').status_code, 400)