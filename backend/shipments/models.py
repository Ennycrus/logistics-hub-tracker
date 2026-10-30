from django.core.exceptions import ValidationError
from django.db import models

from core.models import FailureReason, StatusOption

# The two kinds of shipment the hub reports on. Each kind has its own daily report.
TYPE_BASE = 'base'
TYPE_TEMU = 'temu'
SHIPMENT_TYPE_CHOICES = [
    (TYPE_BASE, 'Base'),
    (TYPE_TEMU, 'TEMU'),
]


class Shipment(models.Model):
    """
    ONE row per waybill, ever. Holds the CURRENT state only.
    Past states live in StatusHistory.
    """

    # Text, not a number: keeps leading zeros. unique=True also creates an index.
    waybill_number = models.CharField(max_length=64, unique=True)
    # Base or TEMU. Set from the waybill prefix when the shipment is imported.
    shipment_type = models.CharField(
        max_length=10, choices=SHIPMENT_TYPE_CHOICES, default=TYPE_TEMU, db_index=True,
    )

    status = models.ForeignKey(
        StatusOption, on_delete=models.PROTECT, related_name='shipments'
    )
    failure_reason = models.ForeignKey(
        FailureReason,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='shipments',
    )
    reason_note = models.TextField(blank=True, help_text='Required when the reason is "Other".')
    notes = models.TextField(blank=True)

    # The date this waybill first entered the system (first scan import).
    first_seen_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def clean(self):
        """Validation rules. Called by the admin and (later) by our services."""
        # Remove accidental spaces around the waybill number.
        self.waybill_number = (self.waybill_number or '').strip()
        if not self.waybill_number:
            raise ValidationError({'waybill_number': 'Waybill number cannot be empty.'})

        # Status not chosen yet: let Django's own "required" error handle it.
        if not self.status_id:
            return

        if self.status.requires_reason:
            if not self.failure_reason_id:
                raise ValidationError(
                    {'failure_reason': f'"{self.status.name}" requires a failure reason.'}
                )
            if self.failure_reason.is_other and not self.reason_note.strip():
                raise ValidationError(
                    {'reason_note': 'Please write the explanation for "Other".'}
                )
        else:
            if self.failure_reason_id:
                raise ValidationError(
                    {'failure_reason': f'"{self.status.name}" should not have a failure reason.'}
                )

    def __str__(self):
        return self.waybill_number


class StatusHistory(models.Model):
    """
    One row for EVERY status change. Rows are only ever added, never edited
    or deleted, so the full story of a shipment is preserved.
    """

    shipment = models.ForeignKey(
        Shipment, on_delete=models.PROTECT, related_name='history'
    )
    old_status = models.ForeignKey(
        StatusOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',  # '+' = no reverse link needed from StatusOption
    )
    new_status = models.ForeignKey(
        StatusOption, on_delete=models.PROTECT, related_name='+'
    )
    failure_reason = models.ForeignKey(
        FailureReason, on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    reason_note = models.TextField(blank=True)
    note = models.TextField(blank=True)

    # The reporting day this change belongs to (can differ from changed_at
    # if you record yesterday's result this morning).
    effective_date = models.DateField()
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at']
        verbose_name_plural = 'Status history'
        indexes = [
            models.Index(fields=['effective_date']),
        ]

    def __str__(self):
        old = self.old_status.name if self.old_status_id else '(new)'
        return f'{self.shipment}: {old} -> {self.new_status} on {self.effective_date}'


class ImportBatch(models.Model):
    """
    One confirmed upload of a scanner spreadsheet.
    The file's fingerprint (hash) is unique, so the same file can't be imported twice.
    """

    file_name = models.CharField(max_length=255)
    # SHA-256 fingerprint of the file's bytes: identical files give identical hashes.
    file_hash = models.CharField(max_length=64, unique=True)
    reporting_date = models.DateField()
    column_index = models.PositiveIntegerField()

    total_rows = models.PositiveIntegerField(default=0)
    new_count = models.PositiveIntegerField(default=0)
    duplicate_in_file_count = models.PositiveIntegerField(default=0)
    # New shipments created by this import, per type.
    base_new_count = models.PositiveIntegerField(default=0)
    temu_new_count = models.PositiveIntegerField(default=0)
    existing_outstanding_count = models.PositiveIntegerField(default=0)
    existing_closed_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)

    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-imported_at']
        verbose_name_plural = 'Import batches'
        indexes = [
            models.Index(fields=['reporting_date']),
        ]

    def __str__(self):
        return f'{self.file_name} ({self.reporting_date})'


class ImportRow(models.Model):
    """One row of an imported file and what happened to it."""

    RESULT_NEW = 'new'
    RESULT_DUPLICATE_IN_FILE = 'duplicate_in_file'
    RESULT_EXISTING_OUTSTANDING = 'existing_outstanding'
    RESULT_EXISTING_CLOSED = 'existing_closed'
    RESULT_INVALID = 'invalid'
    RESULT_CHOICES = [
        (RESULT_NEW, 'New shipment created'),
        (RESULT_DUPLICATE_IN_FILE, 'Duplicate inside the file'),
        (RESULT_EXISTING_OUTSTANDING, 'Already in system, still at hub'),
        (RESULT_EXISTING_CLOSED, 'Already in system, closed (review)'),
        (RESULT_INVALID, 'Invalid / empty'),
    ]

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='rows')
    row_number = models.PositiveIntegerField()
    waybill_number = models.CharField(max_length=255, blank=True)
    result = models.CharField(max_length=30, choices=RESULT_CHOICES)
    message = models.CharField(max_length=255, blank=True)
    # Linked for new and existing shipments; empty for invalid/duplicate rows.
    shipment = models.ForeignKey(
        Shipment, on_delete=models.PROTECT, null=True, blank=True, related_name='import_rows'
    )

    class Meta:
        ordering = ['batch', 'row_number']

    def __str__(self):
        return f'Row {self.row_number}: {self.waybill_number or "(empty)"} - {self.result}'