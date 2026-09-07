from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Profile, WeightLog
from .serializers import AccountSerializer, ProfileSerializer, RegisterSerializer, WeightLogSerializer


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


def _sync_current_weight(user):
    """
    Keeps Profile.current_weight_kg equal to the most recent WeightLog
    entry (by logged_at) so BMI, the nutrition goal calculator, and
    the coach's context builder -- all of which just read that one
    field -- reflect logged history without needing any changes
    themselves. Called after every weight-log create/update/delete.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    latest = WeightLog.objects.filter(user=user).order_by("-logged_at", "-created_at").first()
    profile.current_weight_kg = latest.weight_kg if latest else None
    profile.save(update_fields=["current_weight_kg"])


class WeightLogListCreateView(generics.ListCreateAPIView):
    """
    GET  /accounts/weight-logs/  -- history, most recent first.
    POST /accounts/weight-logs/  -- log a weight. If an entry already
    exists for the given logged_at (defaults to today), it's updated
    in place rather than duplicated -- "what did I weigh that day"
    only has one answer. Always re-syncs Profile.current_weight_kg
    to the latest entry afterward.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WeightLogSerializer

    def get_queryset(self):
        return WeightLog.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logged_at = serializer.validated_data.get("logged_at") or WeightLog._meta.get_field("logged_at").get_default()
        weight_kg = serializer.validated_data["weight_kg"]

        entry, _ = WeightLog.objects.update_or_create(
            user=request.user, logged_at=logged_at, defaults={"weight_kg": weight_kg}
        )
        _sync_current_weight(request.user)
        return Response(WeightLogSerializer(entry).data, status=201)


class WeightLogDetailView(generics.DestroyAPIView):
    """
    DELETE /accounts/weight-logs/<id>/  -- remove a mistaken entry.
    Re-syncs Profile.current_weight_kg to whatever's now most recent
    (or None, if that was the last entry).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WeightLogSerializer

    def get_queryset(self):
        return WeightLog.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        user = instance.user
        instance.delete()
        _sync_current_weight(user)