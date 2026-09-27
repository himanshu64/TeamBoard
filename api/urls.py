from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import KBQueryView, LoginView, RegisterView, UsageSummaryView

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('kb/query/', KBQueryView.as_view(), name='kb-query'),
    path('admin/usage-summary/', UsageSummaryView.as_view(), name='usage-summary'),
]
