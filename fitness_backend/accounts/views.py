import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile, WeightLog
from .serializers import AccountSerializer, ProfileSerializer, RegisterSerializer, WeightLogSerializer
from nutrition.services.goal_calculator import sync_calculated_goals
from .emails import check_verification_code, send_verification_code

logger = logging.getLogger(__name__)
User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /accounts/register/  -- Sign Up Step 1"""

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        # A previous signup attempt that never got verified would hold this
        # email hostage (emails are unique). Nobody could have used that
        # account, so it's safe to discard and start fresh.
        email = (request.data.get("email") or "").strip()
        if email:
            User.objects.filter(email__iexact=email, email_verified=False).delete()
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = serializer.save()
        try:
            send_verification_code(user)
        except Exception:
            logger.exception("Verification email failed for user %s", user.pk)


class VerifyEmailView(APIView):
    """POST /accounts/verify-email/  {"email": "...", "code": "123456"}"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        code = str(request.data.get("code") or "").strip()

        user = User.objects.filter(email__iexact=email, email_verified=False).first()
        if user is None:
            return Response({"error": "Incorrect code."}, status=status.HTTP_400_BAD_REQUEST)

        ok, error = check_verification_code(user, code)
        if not ok:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        user.email_verified = True
        user.verification_code_hash = ""
        user.verification_code_expires = None
        user.verification_attempts = 0
        user.save(
            update_fields=[
                "email_verified",
                "verification_code_hash",
                "verification_code_expires",
                "verification_attempts",
            ]
        )
        return Response({"detail": "Email verified."})


class ResendVerificationView(APIView):
    """POST /accounts/resend-verification/  {"email": "..."}"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email"

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email, email_verified=False).first()
        if user:
            try:
                send_verification_code(user)
            except Exception:
                logger.exception("Resend failed for user %s", user.pk)
        return Response({"detail": "If that account needs verification, a new code was sent."})


class ChangeEmailView(APIView):
    """
    POST /accounts/change-email/
    {"email": "<current>", "password": "...", "new_email": "..."}
    Only for accounts that haven't verified yet; the password proves it's
    the person who just signed up.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email"

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        new_email = (request.data.get("new_email") or "").strip()

        user = User.objects.filter(email__iexact=email, email_verified=False).first()
        if user is None or not user.check_password(password):
            return Response({"error": "Couldn't update that email."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_email(new_email)
        except DjangoValidationError:
            return Response({"error": "Enter a valid email address."}, status=status.HTTP_400_BAD_REQUEST)

        new_email = User.objects.normalize_email(new_email)
        User.objects.filter(email__iexact=new_email, email_verified=False).exclude(pk=user.pk).delete()
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            return Response({"error": "That email is already in use."}, status=status.HTTP_400_BAD_REQUEST)

        user.email = new_email
        user.save(update_fields=["email"])
        try:
            send_verification_code(user)
        except Exception:
            logger.exception("Code send failed after email change for user %s", user.pk)
        return Response({"detail": "Code sent.", "email": user.email})

class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.email_verified:
            raise AuthenticationFailed(
                {"code": "email_not_verified", "detail": "Please verify your email before logging in."}
            )
        return data


class VerifiedTokenObtainPairView(TokenObtainPairView):
    serializer_class = VerifiedTokenObtainPairSerializer

class LogoutView(APIView):
    """
    POST /accounts/logout/  {"refresh": "<refresh token>"}
    Blacklists the given refresh token so it can't be used again --
    without this, ROTATE_REFRESH_TOKENS only issues a new token on use,
    it doesn't revoke the old one, and there was previously no way to
    revoke a token server-side at all (the frontend could only delete
    its local copy). Requires rest_framework_simplejwt.token_blacklist
    in INSTALLED_APPS and BLACKLIST_AFTER_ROTATION=True (see settings.py).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"error": "refresh token is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            # Already invalid/expired/blacklisted -- logout's end state is
            # "this token can't be used," which is already true, so treat
            # it as success rather than surfacing an error for this.
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


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

    def perform_update(self, serializer):
        serializer.save()
        # Height/age/gender/activity level/goal all feed the nutrition
        # goal calculation -- keep it in sync (or flag it for review, if
        # the user has since customized their goals by hand).
        sync_calculated_goals(self.request.user)


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
    sync_calculated_goals(user)


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