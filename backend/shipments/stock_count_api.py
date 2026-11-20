"""
POST /api/stock-count/   (form-data)
    file           the scan of every parcel on the shelves (.xlsx, or a pasted list)
    column         optional, 0-based column number
    all_columns    true = also take waybill numbers found in the other columns
    shipment_type  optional: temu | base (count only one type)

Compares the scan with the app (see services/stock_count.py). Saves NOTHING.
"""

from io import BytesIO

from rest_framework import generics, serializers
from rest_framework.response import Response

from .models import SHIPMENT_TYPE_CHOICES
from .serializers import ImportUploadSerializer
from .services.stock_count import stock_count


class StockCountSerializer(ImportUploadSerializer):
    shipment_type = serializers.ChoiceField(choices=SHIPMENT_TYPE_CHOICES, required=False, allow_blank=True)


class StockCountView(generics.GenericAPIView):
    serializer_class = StockCountSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        upload = data['file']
        result = stock_count(
            BytesIO(upload.read()), column_index=data.get('column'), file_name=upload.name,
            all_columns=data['all_columns'], shipment_type=data.get('shipment_type') or None,
        )
        result['file_name'] = upload.name
        return Response(result)