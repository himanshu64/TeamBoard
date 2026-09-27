from django.core.management.base import BaseCommand

from api.models import KBEntry

C = KBEntry.Category

ENTRIES = [
    # Database / ORM
    ('What is select_related?',
     'select_related follows foreign key and one-to-one relationships with a SQL JOIN, '
     'fetching related objects in the same database query to avoid the N+1 query problem.',
     C.DATABASE),
    ('What is prefetch_related?',
     'prefetch_related runs a separate database query for each many-to-many or reverse '
     'foreign key relationship and joins the results in Python. Use it where select_related cannot.',
     C.DATABASE),
    ('When should I use Q objects?',
     'Use Q objects when a database query needs OR conditions, negation (~Q) or conditions '
     'built dynamically, e.g. Q(question__icontains=term) | Q(answer__icontains=term).',
     C.DATABASE),
    ('How does transaction.atomic() work?',
     'transaction.atomic() wraps a block in a database transaction. If the block raises an '
     'exception every query inside it is rolled back; otherwise it is committed.',
     C.DATABASE),
    ('What is a database index and when should I add one?',
     'An index speeds up query lookups on a column at the cost of slower writes. Add one to '
     'fields you filter, order or join on frequently.',
     C.DATABASE),

    # API
    ('What is a JWT token?',
     'A JSON Web Token is a signed token containing claims such as the user id. The API '
     'verifies the signature on each request, so no server-side session is needed.',
     C.API),
    ('What is the difference between an access token and a refresh token in JWT?',
     'The JWT access token is short-lived and sent with every API request. The refresh token '
     'is longer-lived and only used to obtain a new access token when it expires.',
     C.API),
    ('How do I send a JWT token in an API request?',
     'Send the access token in the Authorization header: "Authorization: Bearer <token>".',
     C.API),
    ('What HTTP status code should an API return for an unauthenticated request?',
     'Return 401 Unauthorized when credentials such as a JWT token are missing or invalid, '
     'and 403 Forbidden when the user is authenticated but lacks permission.',
     C.API),

    # Framework
    ('What is a Django signal?',
     'A signal lets decoupled code react to events, e.g. a post_save receiver on User that '
     'creates a profile whenever a new user is saved to the database.',
     C.FRAMEWORK),
    ('What is a serializer in Django REST Framework?',
     'A serializer converts model instances to JSON for API responses and validates incoming '
     'API data before it is saved to the database.',
     C.FRAMEWORK),
    ('How do permission classes work in Django REST Framework?',
     'Permission classes such as IsAuthenticated run before the view and decide whether the '
     'API request is allowed. They can be set globally in settings or per view.',
     C.FRAMEWORK),

    # Cloud
    ('What is Docker Compose used for?',
     'Docker Compose defines and runs multi-container apps, e.g. a Django API and a Postgres '
     'database, from a single docker-compose.yml file.',
     C.CLOUD),
    ('How should I store secrets in a cloud deployment?',
     'Never commit secrets such as the Django SECRET_KEY or database password. Use environment '
     'variables or a cloud secret manager (AWS Secrets Manager, GCP Secret Manager).',
     C.CLOUD),

    # General
    ('What is the N+1 query problem?',
     'It happens when code runs one query to fetch a list and then one extra database query '
     'per item. Fix it with select_related or prefetch_related.',
     C.GENERAL),
    ('What is the difference between authentication and authorization?',
     'Authentication verifies who the user is (e.g. checking a JWT token); authorization '
     'decides what that user is allowed to do.',
     C.GENERAL),
]


class Command(BaseCommand):
    help = 'Seed the knowledge base with KBEntry records (safe to re-run).'

    def handle(self, *args, **options):
        created = 0
        for question, answer, category in ENTRIES:
            _, was_created = KBEntry.objects.get_or_create(
                question=question,
                defaults={'answer': answer, 'category': category},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {created} new KB entries ({KBEntry.objects.count()} total).'
        ))
