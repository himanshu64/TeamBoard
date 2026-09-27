from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from .models import Company, KBEntry, QueryLog

REGISTER = '/api/auth/register/'
LOGIN = '/api/auth/login/'
REFRESH = '/api/auth/token/refresh/'
QUERY = '/api/kb/query/'
SUMMARY = '/api/admin/usage-summary/'
PASSWORD = 'securepass123'


@override_settings(ALLOWED_HOSTS=['testserver'])
class TeamBoardTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_kb', stdout=StringIO())

    def setUp(self):
        cache.clear()  # throttle counters live in the cache

    def register(self, username='acmecorp', **extra):
        body = {'username': username, 'password': PASSWORD,
                'company_name': 'Acme Corp', 'email': f'{username}@acme.io', **extra}
        return self.client.post(REGISTER, body, format='json')

    def auth_as(self, username='acmecorp', role=None):
        response = self.register(username)
        if role:
            Company.objects.filter(user__username=username).update(role=role)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data

    def query(self, search):
        return self.client.post(QUERY, {'search': search}, format='json')


class SignalTests(TeamBoardTestCase):
    def test_company_created_once_with_api_key(self):
        user = User.objects.create_user('sig', 'sig@x.io', PASSWORD)
        self.assertEqual(len(user.company.api_key), 43)
        self.assertEqual(user.company.role, Company.Role.CLIENT)

        user.first_name = 'changed'
        user.save()  # an update must not create a second profile
        self.assertEqual(Company.objects.filter(user=user).count(), 1)


class AuthTests(TeamBoardTestCase):
    # Scenario 1
    def test_register_returns_api_key_and_tokens(self):
        response = self.register(role='admin')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['username'], 'acmecorp')
        self.assertEqual(response.data['company_name'], 'Acme Corp')
        for key in ('api_key', 'access', 'refresh'):
            self.assertTrue(response.data[key])
        # role in the body is ignored
        self.assertEqual(Company.objects.get(user__username='acmecorp').role, Company.Role.CLIENT)

    # Scenario 2
    def test_duplicate_username_is_400(self):
        self.register()
        response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)

    # Scenario 3
    def test_login_returns_token_and_credentials(self):
        api_key = self.register().data['api_key']
        response = self.client.post(LOGIN, {'username': 'acmecorp', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['api_key'], api_key)
        self.assertEqual(response.data['company_name'], 'Acme Corp')
        self.assertTrue(response.data['access'])

    # Scenario 4
    def test_wrong_password_is_401(self):
        self.register()
        response = self.client.post(LOGIN, {'username': 'acmecorp', 'password': 'nope'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertIn('detail', response.data)

    def test_refresh_token_issues_new_access_token(self):
        refresh = self.register().data['refresh']
        response = self.client.post(REFRESH, {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['access'])

    def test_login_without_company_profile_is_403(self):
        User.objects.create_user('orphan', password=PASSWORD)
        Company.objects.filter(user__username='orphan').delete()
        response = self.client.post(LOGIN, {'username': 'orphan', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_auth_endpoints_are_throttled(self):
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'auth': '2/min', 'kb_query': '60/min'}):
            codes = [self.client.post(LOGIN, {'username': 'x', 'password': 'y'}, format='json').status_code
                     for _ in range(3)]
        self.assertEqual(codes, [401, 401, 429])


class KBQueryTests(TeamBoardTestCase):
    # Scenario 5
    def test_no_token_is_401(self):
        self.assertEqual(self.query('jwt').status_code, 401)

    # Scenario 6 + 11
    def test_results_and_query_log(self):
        self.auth_as()
        response = self.query('select_related')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['search'], 'select_related')
        self.assertGreater(response.data['count'], 0)
        self.assertEqual(len(response.data['results']), response.data['count'])
        self.assertEqual(set(response.data['results'][0]), {'id', 'question', 'answer', 'category'})

        log = QueryLog.objects.get()
        self.assertEqual(log.company.user.username, 'acmecorp')
        self.assertEqual(log.results_count, response.data['count'])

    # Scenario 7 + 11
    def test_no_matches_returns_empty_list_and_still_logs(self):
        self.auth_as()
        response = self.query('zzz-no-such-term')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])
        self.assertEqual(QueryLog.objects.get().results_count, 0)

    # Scenario 8
    def test_missing_or_blank_search_is_400_and_not_logged(self):
        self.auth_as()
        self.assertEqual(self.client.post(QUERY, {}, format='json').status_code, 400)
        self.assertEqual(self.query('   ').status_code, 400)
        self.assertFalse(QueryLog.objects.exists())

    def test_natural_language_query_matches_keywords(self):
        self.auth_as()
        response = self.query('how to use select_related')
        self.assertGreater(response.data['count'], 0)
        self.assertEqual(response.data['results'][0]['question'], 'What is select_related?')

    def test_results_ranked_by_relevance(self):
        self.auth_as()
        response = self.query('JWT token refresh')
        top = response.data['results'][0]['question'].lower()
        self.assertIn('refresh', top)
        self.assertIn('jwt', top)

    def test_search_terms_are_normalized_in_log(self):
        self.auth_as()
        self.query('  JWT ')
        self.query('jwt')
        self.assertEqual(set(QueryLog.objects.values_list('search_term', flat=True)), {'jwt'})

    def test_results_are_paginated(self):
        self.auth_as()
        total = self.query('database').data['count']
        response = self.client.post(f'{QUERY}?limit=2', {'search': 'database'}, format='json')
        self.assertEqual(response.data['count'], total)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])

    def test_api_key_authentication(self):
        api_key = self.register().data['api_key']
        response = self.client.post(QUERY, {'search': 'jwt'}, format='json', HTTP_X_API_KEY=api_key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(QueryLog.objects.get().company.api_key, api_key)

    def test_invalid_api_key_is_401(self):
        response = self.client.post(QUERY, {'search': 'jwt'}, format='json', HTTP_X_API_KEY='bogus')
        self.assertEqual(response.status_code, 401)

    def test_kb_query_is_throttled(self):
        self.auth_as()
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'auth': '20/min', 'kb_query': '2/min'}):
            codes = [self.query('jwt').status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class UsageSummaryTests(TeamBoardTestCase):
    # Scenario 9
    def test_client_is_403(self):
        self.auth_as()
        self.assertEqual(self.client.get(SUMMARY).status_code, 403)

    def test_no_token_is_401(self):
        self.assertEqual(self.client.get(SUMMARY).status_code, 401)

    # Scenario 10
    def test_admin_gets_stats(self):
        self.auth_as('client1')
        for term in ['jwt', 'JWT', 'select_related', 'q objects']:
            self.query(term)
        self.auth_as('client2')
        self.query('jwt')

        self.auth_as('boss', role=Company.Role.ADMIN)
        response = self.client.get(SUMMARY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_queries'], 5)
        self.assertEqual(response.data['active_companies'], 2)
        self.assertEqual(response.data['top_search_terms'][0], {'search_term': 'jwt', 'count': 3})

    def test_date_range_filter(self):
        self.auth_as()
        self.query('jwt')
        QueryLog.objects.update(queried_at=timezone.now() - timedelta(days=10))
        self.query('select_related')

        self.auth_as('boss', role=Company.Role.ADMIN)
        today = timezone.now().date().isoformat()
        response = self.client.get(SUMMARY, {'from': today})
        self.assertEqual(response.data['total_queries'], 1)
        self.assertEqual(response.data['top_search_terms'], [{'search_term': 'select_related', 'count': 1}])

    def test_invalid_date_range_is_400(self):
        self.auth_as('boss', role=Company.Role.ADMIN)
        self.assertEqual(self.client.get(SUMMARY, {'from': 'not-a-date'}).status_code, 400)
        self.assertEqual(self.client.get(SUMMARY, {'from': '2026-02-01', 'to': '2026-01-01'}).status_code, 400)


class EnsureCompanyProfilesTests(TeamBoardTestCase):
    def test_backfills_missing_profiles(self):
        user = User.objects.create_user('legacy', 'legacy@x.io', PASSWORD)
        Company.objects.filter(user=user).delete()

        call_command('ensure_company_profiles', stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.company.company_name, 'legacy@x.io')
        self.assertEqual(len(user.company.api_key), 43)

        call_command('ensure_company_profiles', stdout=StringIO())  # idempotent
        self.assertEqual(Company.objects.filter(user=user).count(), 1)
