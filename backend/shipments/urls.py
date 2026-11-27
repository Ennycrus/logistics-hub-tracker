from django.urls import path

from . import returns_api, stock_count_api, views

urlpatterns = [
    path('shipments/', views.ShipmentList.as_view(), name='shipment-list'),
    path('shipments/bulk-status/', views.ShipmentBulkStatusChange.as_view(), name='shipment-bulk-status'),
    path('shipments/export/', views.ShipmentExport.as_view(), name='shipment-export'),
    path('shipments/<int:pk>/', views.ShipmentDetail.as_view(), name='shipment-detail'),
    path('shipments/<int:pk>/status/', views.ShipmentStatusChange.as_view(), name='shipment-status'),
    path('shipments/<int:pk>/notes/', views.ShipmentNotes.as_view(), name='shipment-notes'),

    path('imports/', views.ImportBatchList.as_view(), name='import-list'),
    path('imports/preview/', views.ImportPreview.as_view(), name='import-preview'),
    path('imports/confirm/', views.ImportConfirm.as_view(), name='import-confirm'),
    path('imports/<int:pk>/', views.ImportBatchDetail.as_view(), name='import-detail'),

    path('stock-count/', stock_count_api.StockCountView.as_view(), name='stock-count'),
    path('stock-count/pending/', stock_count_api.StockPendingList.as_view(), name='stock-count-pending'),

    path('returns/pending/', returns_api.ReturnsPending.as_view(), name='returns-pending'),
    path('returns/mark-emailed/', returns_api.MarkReturnsEmailed.as_view(), name='returns-mark-emailed'),
]