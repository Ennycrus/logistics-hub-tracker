"""
Tests for the reset_data command.

Run with:  python manage.py test shipments
"""

import datetime
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from core.models import FailureReason, HubConfig, StatusOption
from reports.models import DailyReport, ReportingDay
from reports.services.report_service import finalize, get_or_create_draft, save_draft, start_correction

from .models import ImportBatch, Shipment, StatusHistory, TYPE_BASE
from .services.import_service import confirm_import
from .services.status_service import create_shipment
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)


class ResetDataTests(TransactionTestCase):
    # Real commits, like a real run (the backup needs them). serialized_rollback
    # puts the starting statuses and reasons back afterwards.
    serialized_rollback = True

    def setUp(self):
        self.backups = tempfile.mkdtemp()
        User.objects.create_user('admin')
        confirm_import(make_xlsx([['303400000001'], ['100000000001']]), reporting_date=MON)
        create_shipment('000123', first_seen_date=MON, shipment_type=TYPE_BASE)
        report = finalize(save_draft(get_or_create_draft(MON), vans=1, bikes=1, third_party=0),
                          accept_warnings=True)
        finalize(save_draft(start_correction(MON, 'fix'), vans=2), accept_warnings=True)
        self.assertEqual(report.version, 1)

    def reset(self, *args):
        out = StringIO()
        call_command('reset_data', '--backup-dir', self.backups, *args, stdout=out)
        return out.getvalue()

    def test_deletes_data_but_keeps_settings_and_users(self):
        statuses, reasons = StatusOption.objects.count(), FailureReason.objects.count()
        output = self.reset('--yes')

        for model in (Shipment, StatusHistory, ImportBatch, ReportingDay, DailyReport):
            self.assertEqual(model.objects.count(), 0, model.__name__)
        self.assertEqual(StatusOption.objects.count(), statuses)
        self.assertEqual(FailureReason.objects.count(), reasons)
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertTrue(HubConfig.objects.exists())
        self.assertIn('Backup saved', output)

    def test_wrong_answer_deletes_nothing(self):
        with mock.patch('builtins.input', return_value='no'):
            with self.assertRaises(CommandError):
                self.reset()
        self.assertEqual(Shipment.objects.count(), 3)

    def test_typing_delete_confirms(self):
        with mock.patch('builtins.input', return_value='DELETE'):
            self.reset()
        self.assertEqual(Shipment.objects.count(), 0)

    def test_waybills_can_be_imported_again_after_reset(self):
        self.reset('--yes')
        batch = confirm_import(make_xlsx([['303400000001'], ['100000000001']]), reporting_date=MON)
        self.assertEqual(batch.new_count, 2)