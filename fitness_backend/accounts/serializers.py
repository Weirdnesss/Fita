from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Profile

Account = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Handles Sign Up - Step 1 (name, email, password)."""

    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = Account
        fields = ["id", "email", "first_name", "last_name", "password", "confirm_password"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = Account.objects.create_user(password=password, **validated_data)
        # Empty profile shell so Steps 2 & 3 can PATCH into it later
        Profile.objects.create(user=user)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    """Handles Sign Up - Steps 2 & 3, and the Edit Profile screen."""

    bmi = serializers.ReadOnlyField()
    height_cm = serializers.ReadOnlyField()

    class Meta:
        model = Profile
        fields = [
            "gender",
            "activity_level",
            "current_weight_kg",
            "goal_weight_kg",
            "height_ft",
            "height_in",
            "primary_goal",
            "medical_conditions",
            "food_allergies",
            "workout_frequency",
            "workout_location",
            "bmi",
            "height_cm",
        ]


class AccountSerializer(serializers.ModelSerializer):
    """Full profile view: combines Account + nested Profile."""

    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = Account
        fields = ["id", "email", "first_name", "last_name", "profile"]
