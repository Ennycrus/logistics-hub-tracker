"""
Settings API: hub configuration, statuses and failure reasons.

Nothing here can be deleted. Statuses and reasons are switched off instead,
so old shipments and history keep pointing at something real.
"""

from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FailureReason, HubConfig, StatusOption
from .serializers import HubConfigSerializer, ReasonSettingsSerializer, StatusSettingsSerializer


class HubSettings(APIView):
    """
    GET   /api/settings/hub/
    PATCH /api/settings/hub/   {"hub_name": "...", "reasons_format": "grouped" | "text"}
    """

    def get(self, request):
        return Response(HubConfigSerializer(HubConfig.get()).data)

    def patch(self, request):
        serializer = HubConfigSerializer(HubConfig.get(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StatusSettingsList(generics.ListCreateAPIView):
    """GET (all, including switched off) and POST /api/settings/statuses/"""

    queryset = StatusOption.objects.all()
    serializer_class = StatusSettingsSerializer
    pagination_class = None


class StatusSettingsDetail(generics.RetrieveUpdateAPIView):
    """GET and PATCH /api/settings/statuses/<id>/  (no DELETE)"""

    queryset = StatusOption.objects.all()
    serializer_class = StatusSettingsSerializer


class ReasonSettingsList(generics.ListCreateAPIView):
    """GET (all, including switched off) and POST /api/settings/reasons/"""

    queryset = FailureReason.objects.all()
    serializer_class = ReasonSettingsSerializer
    pagination_class = None


class ReasonSettingsDetail(generics.RetrieveUpdateAPIView):
    """GET and PATCH /api/settings/reasons/<id>/  (no DELETE)"""

    queryset = FailureReason.objects.all()
    serializer_class = ReasonSettingsSerializer