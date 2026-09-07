from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import MeView, ProfileView, RegisterView, WeightLogDetailView, WeightLogListCreateView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("login/refresh/", TokenRefreshView.as_view(), name="login-refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("me/", MeView.as_view(), name="me"),
    path("weight-logs/", WeightLogListCreateView.as_view(), name="weight-log-list"),
    path("weight-logs/<int:pk>/", WeightLogDetailView.as_view(), name="weight-log-detail"),
]