from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Profile, WeightLog

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
    age = serializers.ReadOnlyField()

    # current_weight_kg is now fully derived -- Signup Step 2 logs the
    # initial baseline through POST /accounts/weight-logs/ (see
    # Signup.jsx) instead of writing this field directly, so nothing
    # writes it anymore except _sync_current_weight() in views.py.
    # goal_weight_kg keeps its own upper bound below since it's still
    # a plain editable field.
    current_weight_kg = serializers.ReadOnlyField()
    goal_weight_kg = serializers.FloatField(required=False, allow_null=True, min_value=20, max_value=300)

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        from datetime import date

        today = date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth can't be in the future.")
        age_years = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age_years > 120:
            raise serializers.ValidationError("That date of birth doesn't look right.")
        return value

    class Meta:
        model = Profile
        fields = [
            "gender",
            "date_of_birth",
            "age",
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


class WeightLogSerializer(serializers.ModelSerializer):
    """A single logged bodyweight entry. See WeightLog on the model."""

    weight_kg = serializers.FloatField(min_value=20, max_value=300)

    class Meta:
        model = WeightLog
        fields = ["id", "weight_kg", "logged_at", "created_at"]
        read_only_fields = ["id", "created_at"]