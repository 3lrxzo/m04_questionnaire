"""
Django settings — M04 健康問卷模組

機敏設定（SECRET_KEY、DB 帳密）一律由 .env 讀入，不寫死在本檔。
.env 不進版控，各機器依 .env.example 自行建立。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# --- 核心 ---------------------------------------------------------------

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

# 本機開發時 127.0.0.1 被所有專案共用，cookie 是跟著主機不跟著 port。
# 用專案專屬名稱，避免別的本機 Django 專案的 sessionid / csrftoken
# 互相蓋掉（症狀：CSRF cookie has incorrect length、莫名被登出）。
SESSION_COOKIE_NAME = "m04_sessionid"
CSRF_COOKIE_NAME = "m04_csrftoken"

# Django 4.0+ 會比對請求的 Origin 標頭。填答頁的 fetch 是同源請求，
# 但瀏覽器送出的 Origin 可能帶或不帶 port，兩種都列入信任。
# 正式部署時由 .env 設定真實網域（含 https://）。
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1,http://localhost",
)


# --- 應用程式 -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 第三方
    "rest_framework",
    # 本專案
    "accounts.apps.AccountsConfig",
    "children.apps.ChildrenConfig",
    "questionnaires.apps.QuestionnairesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- 資料庫 -------------------------------------------------------------
# PostgreSQL：問卷 schema 的彈性欄位與填答內容使用 JSONB 儲存

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME", "m04_questionnaire"),
        "USER": os.getenv("DATABASE_USER", ""),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", ""),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
    }
}


# --- 認證 ---------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# 家長端登入／註冊（@login_required 導向這裡）。
# 醫護端頁面用 @staff_member_required，會自行導向 /admin/login/。
# 院方 APP 介接後，家長身分改由 APP 帶入，這套帳密流程僅供展示與測試。
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/parent/"
LOGOUT_REDIRECT_URL = "/"


# --- 在地化 -------------------------------------------------------------
# 後台使用者為兒科部人員，介面與時間一律為正體中文／台北時區

LANGUAGE_CODE = "zh-hant"

TIME_ZONE = "Asia/Taipei"

USE_I18N = True

USE_TZ = True


# --- 靜態檔 -------------------------------------------------------------
# Vue 3 / HTMX / Alpine.js 皆由 CDN 引入，此處僅放本專案自己的 js/css

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# --- DRF ----------------------------------------------------------------
# 家長端填答 API 的權限策略待家長身分驗證機制確定後再收斂，
# 目前先要求登入，避免預設全開。

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# ============================================================
# 金寶貝 API
# ============================================================

GOLDEN_BABY_API_URL = os.getenv(
    "GOLDEN_BABY_API_URL",
    "https://icare.docter.pro/back-end/app",
)

GOLDEN_BABY_API_ACCOUNT = os.getenv(
    "GOLDEN_BABY_API_ACCOUNT",
    "",
)

GOLDEN_BABY_API_PASSWORD = os.getenv(
    "GOLDEN_BABY_API_PASSWORD",
    "",
)
GOLDEN_BABY_API_MOCK = os.getenv(
    "GOLDEN_BABY_API_MOCK",
    "true",
).lower() == "true"