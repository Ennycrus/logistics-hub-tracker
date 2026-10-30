from rest_framework import generics

from .models import FailureReason, StatusOption
from .serializers import FailureReasonSerializer, StatusOptionSerializer


class StatusOptionList(generics.ListAPIView):
    """GET /api/statuses/ -> the options for the status dropdown (active only)."""

    queryset = StatusOption.objects.filter(is_active=True)
    serializer_class = StatusOptionSerializer
    pagination_class = None  # short list: return it all at once


class FailureReasonList(generics.ListAPIView):
    """GET /api/reasons/ -> the options for the reason dropdown (active only)."""

    queryset = FailureReason.objects.filter(is_active=True)
    serializer_class = FailureReasonSerializer
    pagination_class = None