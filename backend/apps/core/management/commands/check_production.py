"""
Production readiness audit (Phase E).

    python manage.py check_production

Validates the ENVIRONMENT (not the currently booted settings module)
against the full production contract -- every variable the deployment
needs, the security guards in config/settings/production.py, and the
known-insecure placeholder values from .env.example -- and prints a
clear bilingual (English/Persian) PASS/WARN/FAIL list. Exits non-zero
if anything FAILs, so it can gate a deploy script or CI.

Deliberately runnable from DEVELOPMENT settings: its whole purpose is
preflight ("will this .env boot and behave correctly in production?"),
and production settings refuse to import when misconfigured -- a tool
that only runs inside a healthy production boot could never explain a
broken one. The last check actually (re-)imports the production module
under the current environment and reports its boot guards verbatim.

Run it on the server after every .env change:

    docker compose -f docker-compose.prod.yml exec backend \
        python manage.py check_production
"""
import importlib
import os
import sys

from django.core.management.base import BaseCommand

# Values shipped in .env.example / defaults that must never reach a
# production server unchanged.
INSECURE_DEFAULTS = {
    "SECRET_KEY": {"", "unsafe-development-secret-key-do-not-use-in-production"},
    "POSTGRES_PASSWORD": {"", "change-me-before-deploying", "cusin_password"},
}

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _env(name, default=""):
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name):
    return [part.strip() for part in _env(name).split(",") if part.strip()]


class Command(BaseCommand):
    help = (
        "Validate the environment against the production contract and print a "
        "bilingual PASS/WARN/FAIL readiness report. Exit code 1 on any FAIL."
    )

    def handle(self, *args, **options):
        results = []

        def add(status, en, fa):
            results.append((status, en, fa))

        # --- Django core -----------------------------------------------------
        secret_key = _env("SECRET_KEY")
        if secret_key in INSECURE_DEFAULTS["SECRET_KEY"]:
            add(FAIL,
                "SECRET_KEY is missing or the development default.",
                "کلید مخفی تنظیم نشده یا همان مقدار پیش‌فرض توسعه است.")
        else:
            add(PASS, "SECRET_KEY is set and not the development default.",
                "کلید مخفی تنظیم شده و پیش‌فرض نیست.")

        if _env("DJANGO_SETTINGS_MODULE") != "config.settings.production":
            add(WARN,
                "DJANGO_SETTINGS_MODULE is not config.settings.production (fine for a "
                "preflight from a dev shell; the server itself must boot production).",
                "DJANGO_SETTINGS_MODULE روی production نیست (برای پیش‌بررسی از محیط توسعه "
                "اشکالی ندارد، اما سرور باید با production بالا بیاید).")
        else:
            add(PASS, "DJANGO_SETTINGS_MODULE=config.settings.production.",
                "ماژول تنظیمات روی production است.")

        if _env_bool("DEBUG", False):
            add(WARN,
                "DEBUG is set true in the environment; the production module forces it "
                "False regardless, but the variable should be removed.",
                "در محیط DEBUG=True است؛ ماژول production آن را به‌صورت اجباری False می‌کند، "
                "ولی بهتر است این متغیر حذف شود.")

        # --- Hosts / CORS / CSRF ----------------------------------------------
        allowed_hosts = _env_list("ALLOWED_HOSTS")
        if not allowed_hosts:
            add(WARN,
                "ALLOWED_HOSTS not set in env; production defaults to cusin.ir,www.cusin.ir.",
                "ALLOWED_HOSTS در env تنظیم نشده؛ در production به‌طور پیش‌فرض cusin.ir,www.cusin.ir است.")
        elif "*" in allowed_hosts:
            add(FAIL, "ALLOWED_HOSTS contains '*' -- never acceptable in production.",
                "ALLOWED_HOSTS شامل '*' است — در production هرگز قابل قبول نیست.")
        else:
            add(PASS, f"ALLOWED_HOSTS: {', '.join(allowed_hosts)}.",
                "ALLOWED_HOSTS صریحاً تنظیم شده است.")

        cors_origins = _env_list("CORS_ALLOWED_ORIGINS")
        if not cors_origins:
            add(FAIL,
                "CORS_ALLOWED_ORIGINS is empty; production refuses to boot without an "
                "explicit allow-list.",
                "CORS_ALLOWED_ORIGINS خالی است؛ production بدون فهرست صریح بالا نمی‌آید.")
        elif "*" in cors_origins or any("*" in o for o in cors_origins):
            add(FAIL, "CORS_ALLOWED_ORIGINS contains a wildcard.",
                "CORS_ALLOWED_ORIGINS شامل wildcard است.")
        else:
            add(PASS, f"CORS allow-list: {', '.join(cors_origins)}.",
                "فهرست مجاز CORS صریحاً تنظیم شده است.")

        if not _env_list("CSRF_TRUSTED_ORIGINS"):
            add(WARN,
                "CSRF_TRUSTED_ORIGINS not set in env; production defaults to "
                "https://cusin.ir,https://www.cusin.ir.",
                "CSRF_TRUSTED_ORIGINS در env تنظیم نشده؛ پیش‌فرض production دامنهٔ cusin.ir است.")
        else:
            add(PASS, "CSRF_TRUSTED_ORIGINS set explicitly.",
                "CSRF_TRUSTED_ORIGINS صریحاً تنظیم شده است.")

        # --- Database -----------------------------------------------------------
        database_url = _env("DATABASE_URL")
        if database_url:
            if database_url.startswith("sqlite"):
                add(FAIL, "DATABASE_URL points at SQLite; PostgreSQL is required.",
                    "DATABASE_URL به SQLite اشاره دارد؛ PostgreSQL الزامی است.")
            else:
                add(PASS, "DATABASE_URL configured.", "DATABASE_URL تنظیم شده است.")
        elif _env("POSTGRES_DB") and _env("POSTGRES_USER") and _env("POSTGRES_HOST"):
            add(PASS, "Discrete POSTGRES_* database settings configured.",
                "تنظیمات جداگانهٔ POSTGRES_* پیکربندی شده‌اند.")
        else:
            add(FAIL,
                "No database configuration found (neither DATABASE_URL nor POSTGRES_*).",
                "هیچ پیکربندی پایگاه داده یافت نشد (نه DATABASE_URL نه POSTGRES_*).")

        if _env("POSTGRES_PASSWORD") in INSECURE_DEFAULTS["POSTGRES_PASSWORD"] and not database_url:
            add(FAIL,
                "POSTGRES_PASSWORD is empty or the documented placeholder -- change it "
                "before deploying.",
                "رمز پایگاه داده خالی یا همان مقدار نمونهٔ مستندات است — پیش از استقرار عوض شود.")

        # --- Redis ----------------------------------------------------------------
        if not _env("REDIS_URL"):
            add(WARN,
                "REDIS_URL not set; production defaults to redis://redis:6379/1 (matches "
                "the compose service). Set it explicitly if Redis lives elsewhere.",
                "REDIS_URL تنظیم نشده؛ پیش‌فرض production همان سرویس redis در compose است.")
        else:
            add(PASS, "REDIS_URL configured.", "REDIS_URL تنظیم شده است.")

        # --- Payments ---------------------------------------------------------------
        gateway = (_env("PAYMENT_GATEWAY") or "mock").lower()
        if gateway == "mock":
            add(FAIL,
                "PAYMENT_GATEWAY is unset or 'mock' -- the mock gateway cannot run in "
                "production (the backend refuses to boot).",
                "درگاه پرداخت mock/خالی است — در production قابل استفاده نیست (بک‌اند بالا نمی‌آید).")
        elif gateway != "zarinpal":
            add(WARN,
                f"PAYMENT_GATEWAY='{gateway}' is not in the registry (mock, zarinpal) -- "
                "unknown gateways fail at first use.",
                f"PAYMENT_GATEWAY='{gateway}' در فهرست درگاه‌ها نیست.")
        else:
            if not _env("PAYMENT_MERCHANT_ID"):
                add(FAIL,
                    "PAYMENT_GATEWAY=zarinpal but PAYMENT_MERCHANT_ID is empty (boot guard).",
                    "درگاه زرین‌پال انتخاب شده ولی کد پذیرنده خالی است.")
            else:
                add(PASS, "ZarinPal merchant id configured.", "کد پذیرندهٔ زرین‌پال تنظیم شده است.")
            if _env_bool("PAYMENT_ZARINPAL_SANDBOX", False):
                add(WARN,
                    "*** PAYMENT_ZARINPAL_SANDBOX=True -- the shop would take NO REAL "
                    "MONEY. Fine for launch rehearsal, fatal for go-live. ***",
                    "*** حالت آزمایشی زرین‌پال روشن است — هیچ پول واقعی دریافت نمی‌شود. برای "
                    "تمرین راه‌اندازی مناسب، برای افتتاحیه حتماً خاموش شود. ***")
            else:
                add(PASS, "ZarinPal sandbox mode is OFF (real payments).",
                    "حالت آزمایشی زرین‌پال خاموش است (پرداخت واقعی).")

        callback_url = _env("PAYMENT_CALLBACK_URL", "https://cusin.ir/payment/callback/")
        if not callback_url.startswith("https://"):
            add(WARN,
                f"PAYMENT_CALLBACK_URL ({callback_url}) is not HTTPS -- browsers and the "
                "PSP need a public, secure callback.",
                "آدرس بازگشت درگاه HTTPS نیست.")
        else:
            add(PASS, f"PAYMENT_CALLBACK_URL: {callback_url}.", "آدرس بازگشت درگاه تنظیم شده است.")

        # --- SMS / notifications ------------------------------------------------------
        if _env_bool("SMS_ENABLED", True):
            provider = (_env("SMS_PROVIDER") or "console").lower()
            if provider == "console":
                add(FAIL,
                    "SMS_ENABLED=True but SMS_PROVIDER is unset/'console' -- the console "
                    "provider cannot run in production (boot guard). Use kavenegar, or "
                    "set SMS_ENABLED=False explicitly.",
                    "SMS روشن است ولی ارائه‌دهنده console/خالی است — در production مجاز نیست. "
                    "kavenegar را تنظیم کنید یا SMS_ENABLED=False بگذارید.")
            elif provider == "kavenegar" and not _env("KAVENEGAR_API_KEY"):
                add(FAIL,
                    "SMS_PROVIDER=kavenegar but KAVENEGAR_API_KEY is empty (boot guard).",
                    "کلید API کاوه‌نگار خالی است.")
            else:
                add(PASS, f"SMS provider '{provider}' configured.",
                    f"ارائه‌دهندهٔ پیامک '{provider}' تنظیم شده است.")
        else:
            add(PASS,
                "SMS_ENABLED=False -- explicit opt-out; phone-only password resets will "
                "log a SKIPPED notification.",
                "SMS صریحاً غیرفعال است؛ بازیابی رمز حساب‌های فقط-موبایلی SKIPPED ثبت می‌شود.")

        if not _env("EMAIL_HOST"):
            add(WARN,
                "EMAIL_HOST is empty -- password-reset links and order notification "
                "emails cannot be delivered (they are logged as SKIPPED).",
                "EMAIL_HOST خالی است — ایمیل‌های بازیابی رمز و اعلان سفارش ارسال نمی‌شوند.")
        else:
            add(PASS, f"SMTP configured ({_env('EMAIL_HOST')}).", "SMTP تنظیم شده است.")

        # --- HTTPS / URLs ---------------------------------------------------------------
        if not _env_bool("HTTPS_ENABLED", False):
            add(WARN,
                "HTTPS_ENABLED=False -- secure-only cookies, SSL redirect and HSTS stay "
                "off. Turn it on once certificates are installed (docs/DEPLOY.md).",
                "HTTPS_ENABLED=False — کوکی‌های امن و HSTS خاموش‌اند. پس از نصب گواهی آن را "
                "روشن کنید (docs/DEPLOY.md).")
        else:
            add(PASS, "HTTPS_ENABLED=True.", "HTTPS فعال است.")

        frontend_url = _env("FRONTEND_URL", "https://cusin.ir")
        if not frontend_url.startswith("https://") and _env_bool("HTTPS_ENABLED", False):
            add(WARN, "FRONTEND_URL is not HTTPS while HTTPS_ENABLED=True.",
                "FRONTEND_URL با وجود فعال بودن HTTPS، از http استفاده می‌کند.")
        else:
            add(PASS, f"FRONTEND_URL: {frontend_url}.", "FRONTEND_URL تنظیم شده است.")

        # --- Monitoring ------------------------------------------------------------------
        if not _env("SENTRY_DSN"):
            add(WARN,
                "SENTRY_DSN is empty -- error monitoring is off (optional, but strongly "
                "recommended for a live shop).",
                "SENTRY_DSN خالی است — پایش خطا خاموش است (اختیاری ولی توصیه‌شده).")
        else:
            add(PASS, "Sentry DSN configured.", "Sentry تنظیم شده است.")

        if _env_int("ORDER_EXPIRY_HOURS", 24) <= 0:
            add(WARN, "ORDER_EXPIRY_HOURS should be a positive number of hours.",
                "ORDER_EXPIRY_HOURS باید عددی مثبت باشد.")

        # --- The real boot test -------------------------------------------------------------
        boot_error = self._production_boot_check()
        if boot_error:
            add(FAIL,
                f"config.settings.production REFUSES to boot with this environment: {boot_error}",
                f"ماژول production با این محیط بالا نمی‌آید: {boot_error}")
        else:
            add(PASS,
                "config.settings.production imports cleanly with this environment.",
                "ماژول تنظیمات production با این محیط بدون خطا import می‌شود.")

        # --- Report ------------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write("== Cusin Gallery production readiness / بررسی آمادگی استقرار ==")
        self.stdout.write("")
        counts = {PASS: 0, WARN: 0, FAIL: 0}
        for status, en, fa in results:
            counts[status] += 1
            if status == PASS:
                line = self.style.SUCCESS(f"[PASS] {en}")
            elif status == WARN:
                line = self.style.WARNING(f"[WARN] {en}")
            else:
                line = self.style.ERROR(f"[FAIL] {en}")
            self.stdout.write(line)
            self.stdout.write(f"       {fa}")
        self.stdout.write("")
        summary = f"RESULT: {counts[PASS]} passed, {counts[WARN]} warning(s), {counts[FAIL]} failed"
        if counts[FAIL]:
            self.stdout.write(self.style.ERROR(summary + " — NOT ready / آماده نیست"))
            sys.exit(1)
        if counts[WARN]:
            self.stdout.write(self.style.WARNING(summary + " — ready with warnings / آماده (با هشدار)"))
        else:
            self.stdout.write(self.style.SUCCESS(summary + " — READY / آماده استقرار"))

    @staticmethod
    def _production_boot_check():
        """(Re-)import config.settings.production under the CURRENT
        environment and return its boot-guard error, if any. Reloading
        base first makes the check honest even when the command runs
        inside a dev-settings process (base.py read the env once at that
        boot). Returns None when production would start cleanly."""
        try:
            base = importlib.import_module("config.settings.base")
            importlib.reload(base)
            production = importlib.import_module("config.settings.production")
            importlib.reload(production)
        except Exception as exc:  # RuntimeError boot guards, or anything else
            return f"{type(exc).__name__}: {exc}"
        return None
