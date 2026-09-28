from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import LogoutView, MeView, ProfileView, RegisterView, WeightLogDetailView, WeightLogListCreateView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", views.ResendVerificationView.as_view(), name="resend-verification"),
    path("login/", views.VerifiedTokenObtainPairView.as_view(), name="login"),
    path("login/refresh/", TokenRefreshView.as_view(), name="login-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("me/", MeView.as_view(), name="me"),
    path("weight-logs/", WeightLogListCreateView.as_view(), name="weight-log-list"),
    path("weight-logs/<int:pk>/", WeightLogDetailView.as_view(), name="weight-log-detail"),
    path("verify-email/", views.VerifyEmailView.as_view()),
    path("resend-verification/", views.ResendVerificationView.as_view()),
    path("change-email/", views.ChangeEmailView.as_view()),
]