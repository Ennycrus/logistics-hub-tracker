from django.urls import path

from . import views

urlpatterns = [
    path('shipments/', views.ShipmentList.as_view(), name='shipment-list'),
    path('shipments/bulk-status/', views.ShipmentBulkStatusChange.as_view(), name='shipment-bulk-status'),
    path('shipments/<int:pk>/', views.ShipmentDetail.as_view(), name='shipment-detail'),
    path('shipments/<int:pk>/status/', views.ShipmentStatusChange.as_view(), name='shipment-status'),
    path('shipments/<int:pk>/notes/', views.ShipmentNotes.as_view(), name='shipment-notes'),

    path('imports/', views.ImportBatchList.as_view(), name='import-list'),
    path('imports/preview/', views.ImportPreview.as_view(), name='import-preview'),
    path('imports/confirm/', views.ImportConfirm.as_view(), name='import-confirm'),
    path('imports/<int:pk>/', views.ImportBatchDetail.as_view(), name='import-detail'),
]