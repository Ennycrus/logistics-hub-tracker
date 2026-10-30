from django.urls import path

from . import views

urlpatterns = [
    path('reports/', views.ReportHistory.as_view(), name='report-history'),
    path('reports/<str:date>/', views.ReportForDate.as_view(), name='report-for-date'),
    path('reports/<str:date>/finalize/', views.FinalizeReport.as_view(), name='report-finalize'),
    path('reports/<str:date>/correct/', views.CorrectReport.as_view(), name='report-correct'),
    path('reports/<str:date>/download/', views.DownloadReport.as_view(), name='report-download'),
    path('reports/<str:date>/shipments/', views.DayShipments.as_view(), name='report-shipments'),
]