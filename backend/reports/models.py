from django.db import models
from django.db.models import Q

from shipments.models import SHIPMENT_TYPE_CHOICES, TYPE_TEMU, Shipment


class ReportingDay(models.Model):
    """
    One row per reporting date AND shipment type: the Base report and the
    TEMU report for the same date are separate days with separate figures.
    While a day is OPEN its shipment list can be refreshed; once FINALIZED
    it never changes again.
    """

    STATE_OPEN = 'open'
    STATE_FINALIZED = 'finalized'
    STATE_CHOICES = [
        (STATE_OPEN, 'Open'),
        (STATE_FINALIZED, 'Finalized'),
    ]

    date = models.DateField()
    shipment_type = models.CharField(max_length=10, choices=SHIPMENT_TYPE_CHOICES, default=TYPE_TEMU)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'shipment_type']
        constraints = [
            models.UniqueConstraint(fields=['date', 'shipment_type'], name='one_day_per_date_and_type'),
        ]

    @property
    def is_open(self):
        return self.state == self.STATE_OPEN

    def __str__(self):
        return f'{self.date} {self.get_shipment_type_display()} ({self.get_state_display()})'


class DailyShipmentRecord(models.Model):
    """
    "This shipment belongs to this day's report, as Inbound or Old Pending."

    The unique constraint on (day, shipment) is what makes it IMPOSSIBLE to
    count the same shipment twice in one day.
    """

    KIND_INBOUND = 'inbound'
    KIND_OLD_PENDING = 'old_pending'
    KIND_CHOICES = [
        (KIND_INBOUND, 'Inbound'),
        (KIND_OLD_PENDING, 'Old Pending'),
    ]

    day = models.ForeignKey(ReportingDay, on_delete=models.CASCADE, related_name='records')
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name='daily_records')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)

    class Meta:
        ordering = ['day', 'kind', 'shipment__waybill_number']
        constraints = [
            models.UniqueConstraint(fields=['day', 'shipment'], name='one_record_per_shipment_per_day'),
        ]

    def __str__(self):
        return f'{self.day.date} - {self.shipment} - {self.get_kind_display()}'


class DailyReport(models.Model):
    """
    The company report for one day.

    - While is_finalized is False it is a DRAFT: you can keep editing it.
    - Once finalized, its figures are FROZEN in `figures` and never change,
      even if shipment statuses change later.
    - A correction never edits a finalized report. It creates a new version
      (version 2, 3, ...) that points back to the one it corrects.
    """

    day = models.ForeignKey(ReportingDay, on_delete=models.PROTECT, related_name='reports')
    version = models.PositiveIntegerField(default=1)
    corrects = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='corrected_by',
    )
    correction_reason = models.TextField(blank=True)

    # Manual inputs. None = "not entered yet" (different from 0).
    vans = models.PositiveIntegerField(null=True, blank=True)
    bikes = models.PositiveIntegerField(null=True, blank=True)
    third_party = models.PositiveIntegerField(null=True, blank=True, verbose_name='3PL')
    reasons_text = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Manual corrections to calculated figures:
    # {"delivered": {"value": 40, "note": "counted at gate"}, ...}
    adjustments = models.JSONField(default=dict, blank=True)

    # The frozen snapshot, filled in when the report is finalized.
    calculated = models.JSONField(default=dict, blank=True)  # what the app worked out
    figures = models.JSONField(default=dict, blank=True)     # what was reported
    warnings = models.JSONField(default=list, blank=True)    # warnings accepted at the time
    hub_name = models.CharField(max_length=100, blank=True)

    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-day__date', '-version']
        constraints = [
            models.UniqueConstraint(fields=['day', 'version'], name='one_report_per_version'),
            # Only one draft at a time for each day.
            models.UniqueConstraint(
                fields=['day'], condition=Q(is_finalized=False), name='one_draft_per_day',
            ),
        ]

    def __str__(self):
        state = 'final' if self.is_finalized else 'draft'
        return f'{self.day.date} v{self.version} ({state})'