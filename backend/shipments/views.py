from io import BytesIO

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImportBatch, Shipment
from .serializers import (
    BulkStatusChangeSerializer, ImportBatchDetailSerializer, ImportBatchSerializer,
    ImportConfirmSerializer, ImportUploadSerializer, NotesSerializer, ShipmentDetailSerializer,
    ShipmentSerializer, StatusChangeSerializer,
)
from .services.excel_reader import preview_scan_file
from .services.import_service import confirm_import, find_previous_import, undo_import
from .services.search import waybill_search
from .services.status_service import bulk_change_status, change_status


class ShipmentList(generics.ListAPIView):
    """
    GET /api/shipments/

    Optional filters (combine as you like):
        ?search=3584        exactly 4 digits: waybill ends with them; otherwise: contains the text
        ?status=3           a status id
        ?category=unchecked a status category (e.g. to find what still needs checking)
        ?type=base          only Base shipments (or ?type=temu)
        ?page=2             next 50 rows
    """

    serializer_class = ShipmentSerializer

    def get_queryset(self):
        queryset = Shipment.objects.select_related('status', 'failure_reason').order_by('waybill_number')
        params = self.request.query_params

        search = waybill_search(params.get('search'))
        if search:
            queryset = queryset.filter(search)
        if params.get('status'):
            queryset = queryset.filter(status_id=params['status'])
        if params.get('category'):
            queryset = queryset.filter(status__category=params['category'])
        if params.get('type'):
            queryset = queryset.filter(shipment_type=params['type'])
        return queryset


class ShipmentDetail(generics.RetrieveAPIView):
    """GET /api/shipments/<id>/ -> one shipment with its full status history."""

    queryset = Shipment.objects.select_related('status', 'failure_reason').prefetch_related(
        'history__old_status', 'history__new_status', 'history__failure_reason',
    )
    serializer_class = ShipmentDetailSerializer


class ShipmentStatusChange(APIView):
    """
    POST /api/shipments/<id>/status/

    Body (JSON):
        {
          "status": 4,
          "failure_reason": 1,          (only when the status needs one)
          "reason_note": "Gate locked", (only when the reason is "Other")
          "note": "optional",
          "effective_date": "2026-10-29" (optional, defaults to today)
        }

    The view stays thin: check the input, call the service, return the result.
    """

    def post(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)

        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        changed = change_status(
            shipment,
            data['status'],
            failure_reason=data.get('failure_reason'),
            reason_note=data['reason_note'],
            note=data['note'],
            effective_date=data.get('effective_date'),
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

        result = bulk_change_status(
            data['shipment_ids'],
            data['status'],
            failure_reason=data.get('failure_reason'),
            reason_note=data['reason_note'],
            note=data['note'],
            effective_date=data.get('effective_date'),
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
        file    the scanner .xlsx
        column  optional, 0-based column number

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
        result = preview_scan_file(BytesIO(data), column_index=serializer.validated_data.get('column'))

        previous = find_previous_import(data)
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
        )
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportBatchList(generics.ListAPIView):
    """GET /api/imports/ -> import history, newest first."""

    queryset = ImportBatch.objects.all()
    serializer_class = ImportBatchSerializer


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