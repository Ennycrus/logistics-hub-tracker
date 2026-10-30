from django.urls import path

from . import auth_views, settings_views, views

urlpatterns = [
    path('auth/csrf/', auth_views.CsrfView.as_view(), name='auth-csrf'),
    path('auth/me/', auth_views.MeView.as_view(), name='auth-me'),
    path('auth/login/', auth_views.LoginView.as_view(), name='auth-login'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='auth-logout'),

    path('statuses/', views.StatusOptionList.as_view(), name='status-list'),
    path('reasons/', views.FailureReasonList.as_view(), name='reason-list'),

    path('settings/hub/', settings_views.HubSettings.as_view(), name='settings-hub'),
    path('settings/statuses/', settings_views.StatusSettingsList.as_view(), name='settings-statuses'),
    path('settings/statuses/<int:pk>/', settings_views.StatusSettingsDetail.as_view(), name='settings-status'),
    path('settings/reasons/', settings_views.ReasonSettingsList.as_view(), name='settings-reasons'),
    path('settings/reasons/<int:pk>/', settings_views.ReasonSettingsDetail.as_view(), name='settings-reason'),
]