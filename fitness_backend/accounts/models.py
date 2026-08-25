from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class AccountManager(BaseUserManager):
    """Custom manager since we use email instead of username for auth."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class Account(AbstractUser):
    """
    Custom user model. Email-based login instead of username.
    Step 1 of signup (name/email/password) lives here; Steps 2-3
    (activity level, goals, medical info) live in Profile below.
    """

    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = AccountManager()

    def __str__(self):
        return self.email


class ActivityLevel(models.TextChoices):
    SEDENTARY = "sedentary", "Sedentary"
    LIGHTLY_ACTIVE = "lightly_active", "Lightly Active"
    MODERATELY_ACTIVE = "moderately_active", "Moderately Active"
    VERY_ACTIVE = "very_active", "Very Active"


class PrimaryGoal(models.TextChoices):
    LOSE_WEIGHT = "lose_weight", "Lose Weight"
    GAIN_WEIGHT = "gain_weight", "Gain Weight"
    MAINTAIN_WEIGHT = "maintain_weight", "Maintain Weight"
    GAIN_MUSCLE = "gain_muscle", "Gain Muscle"
    BUILD_STRENGTH = "build_strength", "Build Strength"


class WorkoutLocation(models.TextChoices):
    GYM = "gym", "Gym"
    HOME = "home", "Home"
    MIXED = "mixed", "Mixed"


class WorkoutFrequency(models.TextChoices):
    ONE_TO_TWO = "1-2", "1-2 Days per week"
    THREE_TO_FOUR = "3-4", "3-4 Days per week"
    FIVE_TO_SIX = "5-6", "5-6 Days per week"
    DAILY = "daily", "Daily"


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"


class Profile(models.Model):
    """
    Steps 2 & 3 of signup. One-to-one with Account so the account
    can be created first (step 1) and this filled in as the wizard
    progresses, matching the multi-step signup flow.
    """

    user = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name="profile"
    )

    # Step 2 - Basic Information
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    activity_level = models.CharField(
        max_length=20, choices=ActivityLevel.choices, blank=True
    )
    current_weight_kg = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(20)]
    )
    goal_weight_kg = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(20)]
    )
    height_ft = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(3), MaxValueValidator(8)],
    )
    height_in = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(11)],
    )
    primary_goal = models.CharField(
        max_length=20, choices=PrimaryGoal.choices, blank=True
    )

    # Step 3 - Additional Information
    medical_conditions = models.TextField(blank=True)
    food_allergies = models.TextField(blank=True)
    workout_frequency = models.CharField(
        max_length=10, choices=WorkoutFrequency.choices, blank=True
    )
    workout_location = models.CharField(
        max_length=10, choices=WorkoutLocation.choices, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def height_cm(self):
        if self.height_ft is None:
            return None
        total_inches = (self.height_ft * 12) + (self.height_in or 0)
        return round(total_inches * 2.54, 1)

    @property
    def bmi(self):
        if not self.current_weight_kg or not self.height_cm:
            return None
        height_m = self.height_cm / 100
        return round(self.current_weight_kg / (height_m**2), 1)

    def __str__(self):
        return f"Profile<{self.user.email}>"
