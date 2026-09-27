from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Company, QueryLog
from .permissions import IsAdminUser
from .search import normalize, search_kb
from .serializers import (
    KBEntrySerializer,
    KBQuerySerializer,
    LoginSerializer,
    RegisterSerializer,
    UsageSummaryFilterSerializer,
)

NO_PROFILE = 'This account has no company profile. Run `python manage.py ensure_company_profiles`.'


def company_for(user):
    try:
        return user.company
    except Company.DoesNotExist:
        raise PermissionDenied(NO_PROFILE)


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


class KBResultsPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            # post_save signal creates the Company and its api_key.
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password'],
            )
            company = user.company
            company.company_name = data['company_name']
            company.save(update_fields=['company_name'])

        return Response({
            'username': user.username,
            'company_name': company.company_name,
            'api_key': company.api_key,
            **tokens_for(user),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = authenticate(
            request,
            username=data['username'],
            password=data['password'],
        )
        if user is None:
            return Response(
                {'detail': 'Invalid username or password.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        company = company_for(user)
        return Response({
            **tokens_for(user),
            'company_name': company.company_name,
            'api_key': company.api_key,
        })


class KBQueryView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kb_query'

    def post(self, request):
        company = company_for(request.user)

        serializer = KBQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        search = serializer.validated_data['search']

        paginator = KBResultsPagination()
        with transaction.atomic():
            page = paginator.paginate_queryset(search_kb(search), request, view=self)
            # Logged even with zero results: billing counts queries made.
            QueryLog.objects.create(
                company=company,
                search_term=normalize(search),
                results_count=paginator.count,
            )

        return Response({
            'search': search,
            'count': paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': KBEntrySerializer(page, many=True).data,
        })


class UsageSummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        params = {'start': request.query_params.get('from'), 'end': request.query_params.get('to')}
        filters = UsageSummaryFilterSerializer(data={k: v for k, v in params.items() if v})
        filters.is_valid(raise_exception=True)

        logs = QueryLog.objects.all()
        if 'start' in filters.validated_data:
            logs = logs.filter(queried_at__date__gte=filters.validated_data['start'])
        if 'end' in filters.validated_data:
            logs = logs.filter(queried_at__date__lte=filters.validated_data['end'])

        total_queries = logs.aggregate(total=Count('id'))['total']
        active_companies = logs.values('company').distinct().count()
        top_search_terms = list(
            logs
            .values('search_term')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        return Response({
            'total_queries': total_queries,
            'active_companies': active_companies,
            'top_search_terms': top_search_terms,
        })
