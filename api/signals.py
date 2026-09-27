import secrets

from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Company


@receiver(pre_save, sender=User)
def mark_new_user(sender, instance, **kwargs):
    # Django sets _state.adding to False before post_save fires, so record
    # whether this save is the first one while the flag is still accurate.
    instance._is_new_user = instance._state.adding


@receiver(post_save, sender=User)
def create_company_profile(sender, instance, **kwargs):
    if getattr(instance, '_is_new_user', False):
        Company.objects.create(
            user=instance,
            company_name=instance.email,  # overwritten by view
            api_key=secrets.token_urlsafe(32)
        )
