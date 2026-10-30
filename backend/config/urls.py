from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    # Our API. Each app owns its own URLs.
    path('api/', include('core.urls')),
    path('api/', include('shipments.urls')),
    path('api/', include('reports.urls')),

    # Adds "Log in" to the browsable API pages.
    path('api-auth/', include('rest_framework.urls')),
]