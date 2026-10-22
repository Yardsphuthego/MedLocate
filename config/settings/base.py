from pathlib import Path
import os
import getpass
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.facilities",
    "apps.medicines",
    "apps.inventory",
    "apps.prescriptions",
    "apps.search",
    "apps.audit",
    "apps.dashboard",
]

UNFOLD = {
    "SITE_TITLE": "MedLocate administration",
    "SITE_HEADER": "MedLocate",
    "SITE_SUBHEADER": "Platform administration",
    "SITE_URL": reverse_lazy("dashboard"),
    "SITE_ICON": lambda request: static("medlocate/img/favicon.svg"),
    "SITE_LOGO": lambda request: static("medlocate/img/medlocate-logo.png"),
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/svg+xml", "href": lambda request: static("medlocate/img/favicon.svg")},
    ],
    "BORDER_RADIUS": "4px",
    "COLORS": {
        "primary": {
            "50": "#eef8fb", "100": "#d8eef6", "200": "#b4dfea",
            "300": "#81c9df", "400": "#48afd0", "500": "#1892ba",
            "600": "#087aa8", "700": "#086488", "800": "#0b526e",
            "900": "#0d455c", "950": "#082e40",
        },
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.dashboard.middleware.WorkspaceAdminFrameMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.accounts.context_processors.staff_facilities",
        "apps.dashboard.context_processors.workspace_context",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("MEDLOCATE_USE_SQLITE") != "1":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "medlocate"),
        "USER": os.getenv("POSTGRES_USER", getpass.getuser()),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Gaborone"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
STOCK_FRESH_HOURS = int(os.getenv("STOCK_FRESH_HOURS", "24"))
STOCK_STALE_HOURS = int(os.getenv("STOCK_STALE_HOURS", "72"))
MAX_INVENTORY_UPLOAD_BYTES = int(os.getenv("MAX_INVENTORY_UPLOAD_BYTES", str(5 * 1024 * 1024)))
PRESCRIPTION_DEFAULT_VALIDITY_HOURS = int(os.getenv("PRESCRIPTION_DEFAULT_VALIDITY_HOURS", "168"))
MEDLOCATE_PUBLIC_URL = os.getenv("MEDLOCATE_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
