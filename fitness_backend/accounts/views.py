from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Profile
from .serializers import AccountSerializer, ProfileSerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /accounts/register/  -- Sign Up Step 1"""

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /accounts/profile/  -- Sign Up Steps 2 & 3, and Edit Profile.
    Always operates on the authenticated user's own profile.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class MeView(APIView):
    """GET /accounts/me/  -- full account + profile, for the Profile page."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(AccountSerializer(request.user).data)
