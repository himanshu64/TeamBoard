from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import Company


class APIKeyAuthentication(BaseAuthentication):
    """Authenticate a company's product by its issued key: `X-API-Key: <api_key>`."""

    header = 'X-API-Key'

    def authenticate(self, request):
        key = request.headers.get(self.header)
        if not key:
            return None  # let other authenticators (or the 401) handle it

        try:
            company = Company.objects.select_related('user').get(api_key=key)
        except Company.DoesNotExist:
            raise AuthenticationFailed('Invalid API key.')

        if not company.user.is_active:
            raise AuthenticationFailed('User is inactive.')

        return (company.user, company)

    def authenticate_header(self, request):
        return self.header
