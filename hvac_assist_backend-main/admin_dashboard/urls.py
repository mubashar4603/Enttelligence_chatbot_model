from django.urls import path

from .views import AdminDashboardOverviewAPIView, DailyActivityAPIView, ExportUsersCSVAPIView, RecentQueriesAPIView, UserManagementAPIView

urlpatterns= [
    path('overview/', AdminDashboardOverviewAPIView.as_view(), name='admin-overview'),
    path('recent-queries/', RecentQueriesAPIView.as_view(), name='recent-queries'),
    path('users/', UserManagementAPIView.as_view(), name='admin-user-management'),
    path('users/export/', ExportUsersCSVAPIView.as_view(), name='admin-user-export'),
    path('daily-activity/', DailyActivityAPIView.as_view(), name='daily-activity'),
]
