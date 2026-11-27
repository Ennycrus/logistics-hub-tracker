import datetime
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Max, Exists, OuterRef
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import StatusOption

from .models import ImportBatch, Shipment, StatusHistory
from .serializers import (
    BulkStatusChangeSerializer, ImportBatchDetailSerializer, ImportBatchSerializer,
    ImportConfirmSerializer, ImportUploadSerializer, NotesSerializer, ShipmentDetailSerializer,
    ShipmentSerializer, StatusChangeSerializer,
)
from .services.attempts import with_attempt_count
from .services.excel_reader import OPEN_CATEGORIES, preview_scan_file
from .services.import_service import confirm_import, find_previous_import, undo_import
from .services.search import waybill_search
from .exports import build_shipments_xlsx
from .services.status_service import bulk_change_status, change_status, is_only_adding_who


def finalized_day_warning(shipments, effective_date, new_status, delivered_by=''):
    """
    A 400 response when the date belongs to a daily report that is already
    finalized (for the type of any of these shipments), or None.

    The change would not appear in that frozen report, but the NEXT day's
    Old Pending would change, so the two would disagree. The website asks
    first and sends allow_finalized_day=true to go ahead.
    """
    from reports.models import ReportingDay  # here, to keep the apps loosely linked

    # Only filling in who delivered: the delivery keeps its own date and no
    # report figure changes, so there is nothing to warn about.
    shipments = [s for s in shipments if not is_only_adding_who(s, new_status, delivered_by)]
    date = effective_date or timezone.localdate()
    types = sorted({s.shipment_type for s in shipments})
    frozen = [
        day.get_shipment_type_display()
        for day in ReportingDay.objects.filter(
            date=date, shipment_type__in=types, state=ReportingDay.STATE_FINALIZED,
        )
        if not day.reports.filter(is_finalized=False).exists()  # no correction in progress
    ]
    if not frozen:
        return None
    names = ' and '.join(frozen)
    return Response(
        {
            'error': (
                f'The {names} report for {date:%a %d %b} is already finalized, so this change will '
                'not appear in it, and the next day\'s Old Pending will no longer match it. '
                'If that report needs fixing, start a correction on the Daily Report page.'
            ),
            'details': {'code': 'finalized_day', 'date': date.isoformat(), 'types': frozen},
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _parse_date(value, field):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({field: 'Use a date like 2026-11-25.'})


class ShipmentList(generics.ListAPIView):
    """
    GET /api/shipments/

    Optional filters (combine as you like):
        ?search=3584        exactly 4 digits: waybill ends with them; otherwise: contains the text
        ?status=3           a status id
        ?category=unchecked a status category (e.g. to find what still needs checking)
        ?type=base          only Base shipments (or ?type=temu)
        ?delivered_by=none  delivered, but nobody recorded as Rider, Captain or 3PL
                            (or rider | captain | 3pl)
        ?stale_days=7       not delivered yet and no status change for 7+ days
        ?hide_delivered=1   leave out delivered shipments
        ?hide_returned=1    leave out shipments that left the hub (Initiated Return / returned to sender)
        ?delivered_from=YYYY-MM-DD / ?delivered_to=YYYY-MM-DD   delivered on/between those dates
        ?ready_for_return=1 still at hub with 3+ failed attempts (ready to initiate return)
        ?page=2             next 50 rows
    """

    serializer_class = ShipmentSerializer

    def get_queryset(self):
        return filter_shipments(self.request.query_params)


def filter_shipments(params):
    """
    The shipments matching the list filters. Shared by the list and the Excel
    export, so the download is always exactly what the page shows.
    """
    queryset = with_attempt_count(
        Shipment.objects.select_related('status', 'failure_reason').order_by('waybill_number')
    )

    search = waybill_search(params.get('search'))
    if search:
        queryset = queryset.filter(search)
    if params.get('status'):
        queryset = queryset.filter(status_id=params['status'])
    if params.get('category'):
        queryset = queryset.filter(status__category=params['category'])
    if params.get('type'):
        queryset = queryset.filter(shipment_type=params['type'])
    if params.get('hide_delivered') == '1':
        queryset = queryset.exclude(status__category=StatusOption.CATEGORY_DELIVERED)
    if params.get('hide_returned') == '1':
        queryset = queryset.exclude(status__category=StatusOption.CATEGORY_LEFT_HUB)
    if params.get('ready_for_return') == '1':
        queryset = queryset.filter(
            attempt_count__gte=settings.RETURN_AFTER_ATTEMPTS,
            status__category__in=OPEN_CATEGORIES,
        )

    delivered_from = params.get('delivered_from')
    delivered_to = params.get('delivered_to')
    if delivered_from or delivered_to:
        # Shipments actually DELIVERED on/between those dates, by the delivery's
        # effective_date (the real delivery day), not when it was entered.
        deliveries = StatusHistory.objects.filter(
            shipment=OuterRef('pk'),
            new_status__category=StatusOption.CATEGORY_DELIVERED,
        )
        if delivered_from:
            deliveries = deliveries.filter(effective_date__gte=_parse_date(delivered_from, 'delivered_from'))
        if delivered_to:
            deliveries = deliveries.filter(effective_date__lte=_parse_date(delivered_to, 'delivered_to'))
        queryset = queryset.filter(Exists(deliveries))

    delivered_by = params.get('delivered_by')
    if delivered_by:
        queryset = queryset.filter(
            status__category=StatusOption.CATEGORY_DELIVERED,
            delivered_by='' if delivered_by == 'none' else delivered_by,
        )

    stale_days = params.get('stale_days')
    if stale_days:
        if not stale_days.isdigit():
            raise ValidationError('stale_days must be a number of days.')
        cutoff = timezone.localdate() - datetime.timedelta(days=int(stale_days))
        queryset = (
            queryset.filter(status__category__in=OPEN_CATEGORIES)
            .annotate(last_change=Max('history__effective_date'))
            .filter(last_change__lte=cutoff)
        )
    return queryset


class ShipmentDetail(generics.RetrieveAPIView):
    """GET /api/shipments/<id>/ -> one shipment with its full status history."""

    queryset = with_attempt_count(
        Shipment.objects.select_related('status', 'failure_reason').prefetch_related(
            'history__old_status', 'history__new_status', 'history__failure_reason',
        )
    )
    serializer_class = ShipmentDetailSerializer


class ShipmentExport(APIView):
    """
    GET /api/shipments/export/  -> the filtered shipments list as an .xlsx file.

    Uses the SAME filters as the list, so the download is exactly what the page
    shows (search, status, type, hidden toggles, delivery-date range...).
    """

    def get(self, request):
        queryset = filter_shipments(request.query_params)
        content = build_shipments_xlsx(queryset)
        today = timezone.localdate().isoformat()
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="shipments_{today}.xlsx"'
        return response


class ShipmentStatusChange(APIView):
    """
    POST /api/shipments/<id>/status/

    Body (JSON):
        {
          "status": 4,
          "failure_reason": 1,          (only when the status needs one)
          "reason_note": "Gate locked", (only when the reason is "Other")
          "delivered_by": "rider",      (for Delivered: rider, captain or 3pl)
          "note": "optional",
          "effective_date": "2026-10-29" (optional, defaults to today)
          "allow_finalized_day": true   (only after the website warned that
                                         that day's report is already finalized)
        }

    The view stays thin: check the input, call the service, return the result.
    """

    def post(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)

        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not data['allow_finalized_day']:
            warning = finalized_day_warning(
                [shipment], data.get('effective_date'), data['status'], data['delivered_by'],
            )
            if warning:
                return warning

        changed = change_status(
            shipment,
            data['status'],
            failure_reason=data.get('failure_reason'),
            reason_note=data['reason_note'],
            note=data['note'],
            effective_date=data.get('effective_date'),
            delivered_by=data['delivered_by'],
            return_waybill=data['return_waybill'],
            allow_clear_return=True,
        )

        shipment.refresh_from_db()
        return Response(
            {'changed': changed, 'shipment': ShipmentSerializer(shipment).data},
            status=status.HTTP_200_OK,
        )


class ShipmentNotes(APIView):
    """
    PATCH /api/shipments/<id>/notes/   {"notes": "Customer asked for evening delivery"}

    Notes are your own reminders. They don't change the status or any report
    figure, so they are saved directly (no history row).
    """

    def patch(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)
        serializer = NotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shipment.notes = serializer.validated_data['notes']
        shipment.save(update_fields=['notes', 'updated_at'])
        return Response(ShipmentSerializer(shipment).data)


class ShipmentBulkStatusChange(APIView):
    """
    POST /api/shipments/bulk-status/

    Body (JSON): the same fields as a single status change, plus
        "shipment_ids": [12, 15, 19]

    All or nothing: if any shipment breaks a rule, nothing is saved and the
    response lists which shipments failed and why.
    """

    def post(self, request):
        serializer = BulkStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not data['allow_finalized_day']:
            chosen = Shipment.objects.filter(pk__in=data['shipment_ids'])
            warning = finalized_day_warning(
                chosen, data.get('effective_date'), data['status'], data['delivered_by'],
            )
            if warning:
                return warning

        result = bulk_change_status(
            data['shipment_ids'],
            data['status'],
            failure_reason=data.get('failure_reason'),
            reason_note=data['reason_note'],
            note=data['note'],
            effective_date=data.get('effective_date'),
            delivered_by=data['delivered_by'],
            return_waybill=data['return_waybill'],
        )

        if result['failures']:
            count = len(result['failures'])
            return Response(
                {
                    'error': f'{count} shipment(s) could not be updated, so nothing was saved.',
                    'details': {'failures': result['failures']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


# --- Imports ---------------------------------------------------------------

class ImportPreview(generics.GenericAPIView):
    """
    POST /api/imports/preview/   (form-data)
        file    the scanner .xlsx, or a .txt/.csv (a list pasted from Google Sheets)
        column       optional, 0-based column number
        all_columns  true = also take waybill numbers found in the other columns

    Reads the file and classifies every row. Saves NOTHING.
    Also says whether this exact file was imported before.
    """

    # Setting serializer_class makes the browsable API show an upload form.
    serializer_class = ImportUploadSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data['file']

        data = upload.read()
        all_columns = serializer.validated_data['all_columns']
        result = preview_scan_file(
            BytesIO(data), column_index=serializer.validated_data.get('column'),
            file_name=upload.name, all_columns=all_columns,
        )

        previous = find_previous_import(data, all_columns)
        result['file_name'] = upload.name
        result['already_imported'] = (
            {'batch_id': previous.pk, 'reporting_date': previous.reporting_date}
            if previous else None
        )
        return Response(result)


class ImportConfirm(generics.GenericAPIView):
    """
    POST /api/imports/confirm/   (form-data)
        file            the same .xlsx you previewed
        reporting_date  e.g. 2026-10-29
        column          optional, 0-based column number
        unknown_type    base | temu | skip - needed only when new waybills
                        start with neither 1 nor 3034
        all_columns     true = also take waybill numbers found in the other columns

    Saves the batch and creates the new shipments (all or nothing).
    """

    serializer_class = ImportConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        batch = confirm_import(
            data['file'],
            reporting_date=data['reporting_date'],
            column_index=data.get('column'),
            file_name=data['file'].name,
            unknown_type=data.get('unknown_type') or None,
            all_columns=data['all_columns'],
        )
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportBatchList(generics.ListAPIView):
    """
    GET /api/imports/              -> import history, newest first.
    GET /api/imports/?week=<date>  -> only the imports whose reporting date is in
                                      that date's week (Monday to Sunday).
    """

    serializer_class = ImportBatchSerializer

    def get_queryset(self):
        queryset = ImportBatch.objects.all()
        week = self.request.query_params.get('week')
        if week:
            try:
                day = datetime.date.fromisoformat(week)
            except ValueError:
                raise ValidationError('week must be a date like 2026-11-20.')
            monday = day - datetime.timedelta(days=day.weekday())
            queryset = queryset.filter(
                reporting_date__range=(monday, monday + datetime.timedelta(days=6)),
            ).order_by('-reporting_date', '-imported_at')
        return queryset


class ImportBatchDetail(generics.RetrieveDestroyAPIView):
    """
    GET    /api/imports/<id>/ -> one batch with every row and its result.
    DELETE /api/imports/<id>/ -> undo the import: removes it and the shipments it created.
                                 Refused (400, nothing deleted) if any of those shipments
                                 has a status update or is in a finalized report.
    """

    queryset = ImportBatch.objects.prefetch_related('rows')
    serializer_class = ImportBatchDetailSerializer

    def destroy(self, request, *args, **kwargs):
        removed = undo_import(self.get_object())
        return Response({'removed_shipments': removed})