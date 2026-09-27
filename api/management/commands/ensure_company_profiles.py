import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from api.models import Company


class Command(BaseCommand):
    help = 'Create a Company profile for every User that lacks one (e.g. users made before the signal existed).'

    def handle(self, *args, **options):
        created = 0
        for user in User.objects.filter(company__isnull=True):
            Company.objects.create(
                user=user,
                company_name=user.email or user.username,
                api_key=secrets.token_urlsafe(32),
            )
            created += 1
            self.stdout.write(f'  created profile for {user.username}')
        self.stdout.write(self.style.SUCCESS(f'Created {created} missing company profile(s).'))
