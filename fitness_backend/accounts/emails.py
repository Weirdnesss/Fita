import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5


def _hash_code(user, code):
    return salted_hmac("fita.email_verification", f"{user.pk}:{code}").hexdigest()


def send_verification_code(user):
    code = f"{secrets.randbelow(10**6):06d}"
    user.verification_code_hash = _hash_code(user, code)
    user.verification_code_expires = timezone.now() + timedelta(minutes=CODE_TTL_MINUTES)
    user.verification_attempts = 0
    user.save(update_fields=["verification_code_hash", "verification_code_expires", "verification_attempts"])
    send_mail(
        subject="Your Fitness Assistant verification code",
        message=(
            f"Hi {user.first_name or 'there'},\n\n"
            f"Your verification code is: {code}\n\n"
            f"It expires in {CODE_TTL_MINUTES} minutes. If you didn't sign up, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def check_verification_code(user, code):
    """Returns (ok, error_message). Counts every wrong guess."""
    if (
        not user.verification_code_hash
        or not user.verification_code_expires
        or user.verification_code_expires < timezone.now()
    ):
        return False, "That code has expired. Request a new one."
    if user.verification_attempts >= MAX_ATTEMPTS:
        return False, "Too many attempts. Request a new code."
    user.verification_attempts += 1
    user.save(update_fields=["verification_attempts"])
    if not constant_time_compare(_hash_code(user, code), user.verification_code_hash):
        return False, "Incorrect code."
    return True, ""