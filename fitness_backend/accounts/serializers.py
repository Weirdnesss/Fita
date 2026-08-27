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
    age = serializers.ReadOnlyField()

    # current_weight_kg/goal_weight_kg already have a MinValueValidator(20)
    # at the model level, but no upper bound -- adding one here. height_ft
    # and height_in are already fully bounded (3-8, 0-11) on the model, so
    # nothing to add for those; the ModelSerializer picks those up as-is.
    current_weight_kg = serializers.FloatField(required=False, allow_null=True, min_value=20, max_value=300)
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
