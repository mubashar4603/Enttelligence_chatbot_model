from django.urls import path
from .views import CustomTokenObtainPairView, ForgotPasswordAPIView, LogoutView, SetPasswordView, CreateUserAPIView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('set-password/<uidb64>/<token>/', SetPasswordView.as_view(), name='set_password'),
    path('create-user/', CreateUserAPIView.as_view(), name='create_user'),
    path('forgot-password/', ForgotPasswordAPIView.as_view(), name='forgot_password'), 
] 