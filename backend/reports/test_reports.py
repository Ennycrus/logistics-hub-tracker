"""
Tests for drafts, manual inputs, finalizing and corrections.

Run with:  python manage.py test reports
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment

from .models import DailyReport, ReportingDay
from .services.day_service import open_or_refresh_day
from .services.report_service import (
    current_report, finalize, get_or_create_draft, preview, save_draft, start_correction,
)

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)


class ReportServiceTests(TestCase):

    def setUp(self):
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')

        # Monday: 2 delivered, 1 unsuccessful. Everything checked, so no warnings.
        for waybill in ['D1', 'D2']:
            change_status(create_shipment(waybill, first_seen_date=MON), self.delivered,
                          effective_date=MON)
        self.u1 = create_shipment('U1', first_seen_date=MON)
        change_status(self.u1, self.unsuccessful, failure_reason=self.unavailable,
                      effective_date=MON)

    def ready_draft(self):
        draft = get_or_create_draft(MON)
        return save_draft(draft, vans=1, bikes=2, third_party=0)

    # --- Drafts and inputs --------------------------------------------------

    def test_draft_is_created_once(self):
        first = get_or_create_draft(MON)
        second = get_or_create_draft(MON)
        self.assertEqual(first.pk, second.pk)

    def test_transport_figures_are_required(self):
        draft = get_or_create_draft(MON)
        self.assertEqual(len(preview(draft)['problems']), 3)
        with self.assertRaises(ValidationError):
            finalize(draft)

    def test_zero_is_a_valid_transport_figure(self):
        draft = self.ready_draft()  # third_party=0
        self.assertEqual(preview(draft)['problems'], [])

    def test_negative_transport_figure_is_rejected(self):
        with self.assertRaises(ValidationError):
            save_draft(get_or_create_draft(MON), vans=-1)

    # --- Manual adjustments -------------------------------------------------

    def test_adjustment_needs_a_note(self):
        with self.assertRaises(ValidationError):
            save_draft(get_or_create_draft(MON), adjust={'delivered': (5, '')})

    def test_total_available_cannot_be_adjusted(self):
        with self.assertRaises(ValidationError):
            save_draft(get_or_create_draft(MON), adjust={'total_available': (99, 'x')})

    def test_adjustment_is_applied_recorded_and_warned(self):
        draft = save_draft(self.ready_draft(), adjust={'inbound': (5, 'Second scanner file')})
        data = preview(draft)

        self.assertEqual(data['calculated']['inbound'], 3)
        self.assertEqual(data['figures']['inbound'], 5)
        self.assertEqual(data['figures']['total_available'], 5)  # still Inbound + Old Pending
        self.assertIn('manual_adjustment', [w['code'] for w in data['warnings']])

    def test_adjustment_can_be_cleared(self):
        draft = save_draft(self.ready_draft(), adjust={'delivered': (9, 'typo test')})
        draft = save_draft(draft, clear_adjust=['delivered'])
        self.assertEqual(preview(draft)['figures']['delivered'], 2)

    # --- Finalizing ---------------------------------------------------------

    def test_finalize_freezes_figures_and_day(self):
        report = finalize(self.ready_draft())

        self.assertTrue(report.is_finalized)
        self.assertEqual(report.figures['total_available'], 3)
        self.assertEqual(report.figures['delivered'], 2)
        self.assertEqual(report.figures['current_day'], 1)
        self.assertEqual(report.reasons_text, 'Customer unavailable - 1')
        self.assertEqual(ReportingDay.objects.get(date=MON).state, ReportingDay.STATE_FINALIZED)

    def test_warnings_must_be_accepted(self):
        create_shipment('NEW', first_seen_date=MON)  # unchecked -> warning
        draft = self.ready_draft()

        with self.assertRaises(ValidationError):
            finalize(draft)
        report = finalize(draft, accept_warnings=True)
        self.assertEqual([w['code'] for w in report.warnings], ['unchecked'])

    def test_finalized_report_does_not_change_when_status_changes_later(self):
        report = finalize(self.ready_draft())
        change_status(self.u1, self.delivered, effective_date=MON)  # late correction to history

        report.refresh_from_db()
        self.assertEqual(report.figures['delivered'], 2)  # snapshot unchanged

    def test_finalized_report_cannot_be_edited(self):
        report = finalize(self.ready_draft())
        with self.assertRaises(ValidationError):
            save_draft(report, vans=5)

    def test_finalized_day_cannot_get_a_new_draft(self):
        finalize(self.ready_draft())
        with self.assertRaises(ValidationError):
            get_or_create_draft(MON)

    def test_finalized_day_list_is_frozen(self):
        finalize(self.ready_draft())
        create_shipment('LATE', first_seen_date=MON)
        with self.assertRaises(ValidationError):
            open_or_refresh_day(MON)

    def test_next_day_still_carries_forward(self):
        finalize(self.ready_draft())
        tuesday, summary = open_or_refresh_day(TUE)
        self.assertEqual(summary['old_pending'], 1)  # U1

    # --- Corrections --------------------------------------------------------

    def test_correction_creates_new_version_and_keeps_original(self):
        original = finalize(self.ready_draft())

        correction = start_correction(MON, 'Vans figure was wrong')
        save_draft(correction, vans=3)
        corrected = finalize(correction)

        original.refresh_from_db()
        self.assertEqual(original.vans, 1)        # untouched
        self.assertEqual(corrected.vans, 3)
        self.assertEqual(corrected.version, 2)
        self.assertEqual(corrected.corrects, original)
        self.assertEqual(current_report(MON), corrected)
        self.assertEqual(DailyReport.objects.filter(day__date=MON).count(), 2)

    def test_correction_needs_a_reason(self):
        finalize(self.ready_draft())
        with self.assertRaises(ValidationError):
            start_correction(MON, '   ')

    def test_correction_needs_a_finalized_report(self):
        with self.assertRaises(ValidationError):
            start_correction(MON, 'Nothing to correct')

    def test_only_one_correction_at_a_time(self):
        finalize(self.ready_draft())
        start_correction(MON, 'First')
        with self.assertRaises(ValidationError):
            start_correction(MON, 'Second')

    def test_correction_draft_is_returned_for_editing(self):
        finalize(self.ready_draft())
        correction = start_correction(MON, 'Fix')
        self.assertEqual(get_or_create_draft(MON).pk, correction.pk)