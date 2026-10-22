from .base import *  # noqa: F403

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

from django.core.exceptions import ImproperlyConfigured
if not os.getenv("POSTGRES_DB") or os.getenv("MEDLOCATE_USE_SQLITE") == "1":
    raise ImproperlyConfigured("Production requires an explicitly configured PostgreSQL database.")
