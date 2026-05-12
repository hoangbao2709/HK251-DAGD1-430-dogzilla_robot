"""Deprecated compatibility helper."""

from django.contrib.auth.models import User

from .models import UserProfile


def get_or_create_user_profile(email: str) -> UserProfile | None:
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
