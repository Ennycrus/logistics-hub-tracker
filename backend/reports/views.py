"""
Reports API. Every URL uses the reporting date, e.g. /api/reports/2026-10-29/.

Base and TEMU are separate reports. Add ?type=base or ?type=temu to any URL
(TEMU is used when you leave it out), e.g. /api/reports/2026-10-29/?type=base

Weekly delivery (Monday-Saturday): /api/reports/weekly/?date=2026-10-29&type=base

The views stay thin: they check the input, call the report service,
and return the result. All the rules live in services/report_service.py.
"""

import datetime

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import HubConfig
from shipments.models import SHIPMENT_TYPE_CHOICES, TYPE_TEMU
from shipments.services.search import waybill_search

from .models import DailyReport, DailyShipmentRecord, ReportingDay
from .serializers import (
    CorrectionSerializer, DailyReportSerializer, DayShipmentSerializer, FinalizeSerializer,
    ReportInputSerializer,
)
from .services.day_service import open_or_refresh_day
from .services.excel_export import export_file_name, export_report_bytes
from .services.report_service import (
    current_report, finalize, get_or_create_draft, preview, save_draft, start_correction,
)
from .services.weekly import weekly_file_name, weekly_summary, weekly_workbook_bytes

XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def parse_date(value):
    """Turn '2026-10-29' from the URL into a date. Future dates are refused."""
    try:
        date = datetime.date.fromisoformat(value)
    except ValueError:
        raise ValidationError('Dates must look like 2026-10-29.')
    if date > timezone.localdate():
        raise ValidationError('You cannot open a report for a future date.')
    return date


def report_type(request):
    """Read ?type=base|temu from the URL. Leaving it out means TEMU."""
    value = request.query_params.get('type', TYPE_TEMU).strip().lower()
    if value not in dict(SHIPMENT_TYPE_CHOICES):
        raise ValidationError('type must be "base" or "temu".')
    return value


def draft_response(draft, http_status=status.HTTP_200_OK):
    """A draft plus its live preview (figures, warnings, problems)."""
    return Response(
        {'state': 'draft', 'report': DailyReportSerializer(draft).data, 'preview': preview(draft)},
        status=http_status,
    )


def finalized_response(report, http_status=status.HTTP_200_OK):
    return Response(
        {'state': 'finalized', 'report': DailyReportSerializer(report).data, 'preview': None},
        status=http_status,
    )


class ReportForDate(APIView):
    """
    GET   /api/reports/<date>/
        Open day     -> the draft (created if needed) and its live preview.
        Finalized    -> the frozen report.
        Correcting   -> the correction draft and its preview.

    PATCH /api/reports/<date>/
        Update the draft. Send only the fields you want to change, e.g.
        {"vans": 2, "bikes": 6, "third_party": 3}
        {"adjust": {"delivered": {"value": 40, "note": "Counted at the gate"}}}
        {"clear_adjust": ["delivered"]}
    """

    def get(self, request, date):
        date = parse_date(date)
        shipment_type = report_type(request)
        day = ReportingDay.objects.filter(date=date, shipment_type=shipment_type).first()

        if day and not day.is_open and not day.reports.filter(is_finalized=False).exists():
            return finalized_response(current_report(date, shipment_type))
        return draft_response(get_or_create_draft(date, shipment_type))

    def patch(self, request, date):
        date = parse_date(date)
        serializer = ReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        draft = get_or_create_draft(date, report_type(request))
        save_draft(
            draft,
            vans=data.get('vans'),
            bikes=data.get('bikes'),
            third_party=data.get('third_party'),
            notes=data.get('notes'),
            reasons_text=data.get('reasons_text'),
            adjust={f: (a['value'], a['note']) for f, a in data.get('adjust', {}).items()},
            clear_adjust=data.get('clear_adjust'),
        )
        return draft_response(draft)


class FinalizeReport(APIView):
    """
    POST /api/reports/<date>/finalize/
        {"accept_warnings": true}   needed only when the preview shows warnings
    """

    def post(self, request, date):
        date = parse_date(date)
        serializer = FinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = finalize(
            get_or_create_draft(date, report_type(request)),
            accept_warnings=serializer.validated_data['accept_warnings'],
        )
        return finalized_response(report)


class CorrectReport(APIView):
    """
    POST /api/reports/<date>/correct/
        {"reason": "Vans figure was wrong"}

    Starts a new draft version. The finalized original is never changed.
    """

    def post(self, request, date):
        date = parse_date(date)
        serializer = CorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        draft = start_correction(
            date, serializer.validated_data['reason'], shipment_type=report_type(request),
        )
        return draft_response(draft, http_status=status.HTTP_201_CREATED)


class DownloadReport(APIView):
    """
    GET /api/reports/<date>/download/?type=base              latest finalized version
    GET /api/reports/<date>/download/?type=base&version=1    a specific version
    """

    def get(self, request, date):
        date = parse_date(date)
        shipment_type = report_type(request)
        version = request.query_params.get('version')

        if version:
            report = DailyReport.objects.filter(
                day__date=date, day__shipment_type=shipment_type, version=version, is_finalized=True,
            ).first()
        else:
            report = current_report(date, shipment_type)
        if report is None:
            raise ValidationError(f'No finalized {shipment_type.upper()} report found for {date}.')

        response = HttpResponse(export_report_bytes(report), content_type=XLSX_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{export_file_name(report)}"'
        return response


class ReportHistory(generics.ListAPIView):
    """
    GET /api/reports/            -> every finalized report (Base and TEMU), newest date first
    GET /api/reports/?type=base  -> only Base reports (or ?type=temu)
    """

    serializer_class = DailyReportSerializer

    def get_queryset(self):
        queryset = (
            DailyReport.objects.filter(is_finalized=True)
            .select_related('day', 'corrects')
            .order_by('-day__date', 'day__shipment_type', '-version')
        )
        if self.request.query_params.get('type'):
            queryset = queryset.filter(day__shipment_type=report_type(self.request))
        return queryset


class DayShipments(generics.ListAPIView):
    """
    GET /api/reports/<date>/shipments/

    The shipments that belong to a day's report, 50 per page.
    An open day is refreshed first, so the list is always up to date.

    Optional filters:
        ?type=base | temu   (TEMU if left out)
        ?kind=old_pending | inbound
        ?category=unchecked | outstanding | delivered | returned | left_hub
        ?search=3584    (exactly 4 digits: waybill ends with them; otherwise: contains)
    Old Pending is sorted longest-waiting first.
    """

    serializer_class = DayShipmentSerializer

    def get_queryset(self):
        date = parse_date(self.kwargs['date'])
        shipment_type = report_type(self.request)
        day = ReportingDay.objects.filter(date=date, shipment_type=shipment_type).first()
        if day is None or day.is_open:
            day, _ = open_or_refresh_day(date, shipment_type)

        records = (
            DailyShipmentRecord.objects.filter(day=day)
            .select_related('day', 'shipment__status', 'shipment__failure_reason')
            .order_by('shipment__first_seen_date', 'shipment__waybill_number')
        )
        params = self.request.query_params
        if params.get('kind'):
            records = records.filter(kind=params['kind'])
        if params.get('category'):
            records = records.filter(shipment__status__category=params['category'])
        search = waybill_search(params.get('search'), field='shipment__waybill_number')
        if search:
            records = records.filter(search)
        return records


class WeeklySummary(APIView):
    """
    GET /api/reports/weekly/?date=2026-10-29&type=base
        The Monday-Saturday delivery week containing that date (default: this week),
        from finalized reports only.
    """

    def get(self, request):
        date = parse_date(request.query_params.get('date') or str(timezone.localdate()))
        return Response(weekly_summary(date, report_type(request)))


class WeeklyDownload(APIView):
    """GET /api/reports/weekly/download/?date=2026-10-29&type=base -> the week as an Excel file."""

    def get(self, request):
        date = parse_date(request.query_params.get('date') or str(timezone.localdate()))
        summary = weekly_summary(date, report_type(request))
        hub_name = HubConfig.get().hub_name
        response = HttpResponse(weekly_workbook_bytes(summary, hub_name), content_type=XLSX_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{weekly_file_name(summary, hub_name)}"'
        return response