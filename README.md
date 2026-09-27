# TeamBoard - B2B Knowledge Base API

TeamBoard is a Django + Django REST Framework backend. Companies register to get an API key, search a shared knowledge base with a JWT, and the platform admin sees usage statistics.

## Tech stack

- Python 3.12+ / Django 6.1 / Django REST Framework
- SimpleJWT for token authentication
- PostgreSQL 17 (via Docker)
- python-dotenv for configuration

## Project layout

```
config/                 Django project (settings, root urls)
api/
  models.py             Company, KBEntry, QueryLog
  signals.py            post_save on User -> creates Company + api_key
  apps.py               connects signals in AppConfig.ready()
  permissions.py        IsAdminUser (checks company.role == ADMIN)
  serializers.py        request validation / response shapes
  views.py              register, login, KB query, usage summary
  authentication.py     APIKeyAuthentication (X-API-Key header)
  search.py             keyword extraction + relevance-ranked KB search
  tests.py              automated tests (python manage.py test api)
  management/commands/
    seed_kb.py                   seeds KB entries
    ensure_company_profiles.py   backfills missing Company profiles
docker-compose.yml      PostgreSQL service
TeamBoard.postman_collection.json
```

## Setup

### 1. Environment variables

All credentials live in `.env`. It is git-ignored and never committed. Copy the template and fill in real values:

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `True` for local development |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts, e.g. `localhost,127.0.0.1` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database credentials (used by both Docker and Django) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Where Django connects, e.g. `localhost` / `5432` |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | Optional token lifetimes (default 30 min / 1 day) |
| `THROTTLE_AUTH` / `THROTTLE_KB_QUERY` | Optional rate limits (default `20/min` / `60/min`) |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### 2. Set up the database (PostgreSQL via Docker)

```bash
docker compose up -d
docker compose ps        # wait until the db service is "healthy"
```

The database is created from the `POSTGRES_*` values in `.env`, and data persists in the `pgdata` volume. To connect from PGAdmin, use host `localhost`, port `POSTGRES_PORT`, and the same user and password.

### 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Apply migrations

```bash
python manage.py migrate
```

This creates the `api_company`, `api_kbentry` and `api_querylog` tables along with Django's built-in tables. It also enables the `pg_trgm` Postgres extension, which the search indexes use.

If users existed before the signal was added (for example, from `createsuperuser`), give them Company profiles with:

```bash
python manage.py ensure_company_profiles
```

### 5. Seed KB entries

```bash
python manage.py seed_kb
```

This loads 16 Q&A entries across all five categories (api, database, cloud, framework, general). Several entries share keywords such as `jwt`, `query` and `database`, so a search returns more than one result. The command is safe to re-run because it skips questions that already exist.

### 6. Run the server

```bash
python manage.py runserver
```

The API is now at `http://localhost:8000/api/`.

### 7. Run the tests

```bash
python manage.py test api
```

There are 25 tests. They cover all 11 assignment scenarios plus the extra features below. Django creates and deletes its own test database, so your data is never touched.

## API

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register/` | Public | Create a company; returns `username`, `company_name`, `api_key`, `access`, `refresh` |
| POST | `/api/auth/login/` | Public | Returns `access`, `refresh`, `company_name`, `api_key` |
| POST | `/api/auth/token/refresh/` | Public | Body `{"refresh": "..."}`; returns a new `access` token |
| POST | `/api/kb/query/` | JWT or API key | Body `{"search": "..."}`; returns `search`, `count`, `next`, `previous`, `results` and writes a QueryLog |
| GET | `/api/admin/usage-summary/` | JWT or API key, admin role | Returns `total_queries`, `active_companies`, `top_search_terms`; optional `?from=YYYY-MM-DD&to=YYYY-MM-DD` |

A protected endpoint accepts either of these headers:

```
Authorization: Bearer <access>      # JWT from register/login
X-API-Key: <api_key>                # the company's issued key, for server-to-server use
```

### How it works

- **Protected by default.** `REST_FRAMEWORK` in `settings.py` sets `JWTAuthentication` + `IsAuthenticated` globally. Register and login opt out with `authentication_classes = []` and `permission_classes = []`.
- **Company profile and API key.** A `post_save` signal on `User` (`api/signals.py`) creates the `Company` and generates `api_key` with `secrets.token_urlsafe(32)`. First creation is detected with `instance._state.adding`. Django resets that flag to `False` before `post_save` runs, so a `pre_save` receiver records it first. The view never sets `api_key`, and `role` always defaults to `client`. A `role` sent in the request body is ignored.
- **Company identity.** The query endpoint takes the company from `request.user.company` (the JWT), never from the request body.
- **Search.** The search is split into keywords, with stopwords such as "how", "to" and "use" dropped. Each keyword becomes `Q(question__icontains=w) | Q(answer__icontains=w)`, and the keyword filters are combined with OR. Results are ranked by how many keywords match, with matches in the question counting extra. So `"how to use select_related"` returns "What is select_related?" first, instead of nothing. Trigram GIN indexes on `UPPER(question)` and `UPPER(answer)` let Postgres answer `icontains` from an index instead of scanning the whole table.
- **Pagination.** Results are paginated with `?limit=` (default 20, max 100) and `?offset=`. `count` is always the total number of matches.
- **Logging.** The search and the `QueryLog` insert run inside one `transaction.atomic()` block. A log row is written even when there are zero results, because billing counts queries made. Search terms are stored lowercased with extra whitespace removed, so `"JWT"` and `" jwt "` count as one term in the top search terms.
- **Rate limiting.** Register and login are limited per IP address (`auth` scope), and KB queries per user (`kb_query` scope). Going over the limit returns 429.
- **Admin check.** `IsAdminUser` (`api/permissions.py`) checks `request.user.company.role == Company.Role.ADMIN`, not `is_staff` or `is_superuser`.
- **Usage summary queries.**
  - `total_queries`: `aggregate(total=Count('id'))`
  - `active_companies`: `values('company').distinct().count()`
  - `top_search_terms`: `values('search_term').annotate(count=Count('id')).order_by('-count')[:5]`

### Making a company an admin

Register a company normally, then in PGAdmin run:

```sql
UPDATE api_company SET role = 'admin'
WHERE user_id = (SELECT id FROM auth_user WHERE username = 'teamboard_admin');
```

The role is read from the database on every request, so the change takes effect immediately.

## Postman collection

Import `TeamBoard.postman_collection.json` into Postman. The **Assignment Scenarios** folder covers scenarios 1-10 of the brief, in order. The **Extra Checks** folder adds edge cases (invalid token, blank search, missing fields, no token on the admin endpoint). It also tests the extra features: token refresh, `X-API-Key` authentication, natural-language search, pagination and date filters.

1. Register a company with username `teamboard_admin` and password `securepass123`, then make it an admin using the SQL above. If you use different credentials, update the `admin_username` and `admin_password` collection variables.
2. Run the collection with the Collection Runner. Scenario 01 generates a fresh username on every run, so the collection can be re-run.
3. **Scenario 11:** after scenarios 6 and 7, check that the query logs were written:

   ```sql
   SELECT * FROM api_querylog ORDER BY queried_at DESC;
   ```

## Known limitations

- **API keys are stored in plain text.** The brief requires login to return the `api_key`, and a hashed key couldn't be shown again. A production system would store only a hash and show the key once, at registration.
- **Rate limits are stored per process.** Throttle counters use Django's default in-memory cache, so each server process counts separately. With several workers, use a shared cache such as Redis.
