# راهنمای راه‌اندازی و نگهداری سرور کازین گالری

این راهنما برای **صاحب فروشگاه (بدون دانش برنامه‌نویسی)** نوشته شده است و قدم‌به‌قدم
از خرید سرور تا فروشگاهِ در حال کار را توضیح می‌دهد. هر جا دستور ترمینالی لازم است،
عیناً نوشته شده — کافی است کپی/پیست کنید. اگر جایی گیر کردید، بخش «خرابی‌های رایج»
و در نهایت `docs/PAYMENTS.md` (بخش فنی پرداخت) را ببینید.

فهرست:

1. [چه چیزهایی لازم دارید](#۱-چه-چیزهایی-لازم-دارید)
2. [انتخاب سرور و دامنه](#۲-انتخاب-سرور-و-دامنه)
3. [تنظیم DNS](#۳-تنظیم-dns)
4. [فایروال و اتصال امن SSH](#۴-فایروال)
5. [نصب Docker](#۵-نصب-docker)
6. [دریافت پروژه](#۶-دریافت-پروژه)
7. [ساخت فایل .env (توضیح هر متغیر)](#۷-ساخت-فایل-env)
8. [اولین استقرار](#۸-اولین-استقرار)
9. [فعال‌سازی SSL (قفل https)](#۹-فعال‌سازی-ssl)
10. [گواهی سلامت استقرار](#۱۰-گواهی-سلامت-استقرار)
11. [اضافه‌کردن محصولات](#۱۱-اضافه‌کردن-محصولات)
12. [زرین‌پال: از آزمایشی به واقعی](#۱۲-زرین‌پال-از-آزمایشی-به-واقعی)
13. [تنظیم پیامک (کاوه‌نگار)](#۱۳-تنظیم-پیامک-کاوه‌نگار)
14. [عملیات روزمره](#۱۴-عملیات-روزمره)
15. [پشتیبان‌گیری (بکاپ)](#۱۵-پشتیبان‌گیری)
16. [به‌روزرسانی سایت](#۱۶-به‌روزرسانی-سایت)
17. [بازگشت به نسخهٔ قبل (Rollback)](#۱۷-بازگشت-به-نسخهٔ-قبل)
18. [بازیابی از بکاپ (Restore)](#۱۸-بازیابی-از-بکاپ)
19. [چک‌لیست پیش از افتتاح](#۱۹-چک‌لیست-پیش-از-افتتاح)
20. [خرابی‌های رایج](#۲۰-خرابی‌های-رایج)
23. [نصب روی شبکه های محدود (اینترنت کند یا آینه های مسدود)](#۲۳-نصب-روی-شبکه-های-محدود-اینترنت-کند-یا-آینه-های-مسدود)
24. [اجرای فروشگاه روی کامپیوتر خودتان بدون Docker (ویندوز)](#۲۴-اجرای-فروشگاه-روی-کامپیوتر-خودتان-بدون-docker-ویندوز)

---

## ۱. چه چیزهایی لازم دارید

| مورد | توضیح |
|---|---|
| یک سرور مجازی (VPS) | Ubuntu 22.04/24.04 — حداقل ۲ گیگ رم، ۲۰ گیگ دیسک، ۱ هستهٔ CPU برای شروع کافی است |
| دامنهٔ `cusin.ir` | ثبت‌شده به نام خودتان (برای دامنهٔ .ir از طریق nic.ir یا ثبت‌کننده‌های ایرانی) |
| حساب زرین‌پال | برای دریافت «کد پذیرنده» (merchant id) — بخش ۱۲ |
| حساب کاوه‌نگار (اختیاری) | برای پیامک‌ها — بخش ۱۳ |
| ایمیل فعال | برای خطاهای Sentry (اختیاری) و دریافت گواهی SSL |

> **توجه:** اینماد و درگاه‌های پرداخت ایرانی ممکن است برای پذیرشِ دامنه/سرور
> شرایط خاصی داشته باشند (مثلاً لزوم میزبانی داخل ایران). پیش از خرید سرور،
> محل میزبانی موردنیاز را از پشتیبانی زرین‌پال و مرکز توسعهٔ تجارت الکترونیکی
> (اینماد) بپرسید.

---

## ۲. انتخاب سرور و دامنه

1. از یک ارائه‌دهندهٔ VPS ایرانی یک سرور با **Ubuntu 24.04** سفارش دهید.
2. در پنل ارائه‌دهنده، «رمز root» یا بهتر از آن **کلید SSH** دریافت کنید.
3. دامنهٔ `cusin.ir` (و در صورت امکان `www.cusin.ir`) باید به نام شما ثبت و
   **قابل ویرایش رکوردهای DNS** باشد.

---

## ۳. تنظیم DNS

در پنل مدیریت دامنه، دو رکورد بسازید (`YOUR_SERVER_IP` = آی‌پی سرورتان):

| نوع | نام | مقدار |
|---|---|---|
| A | `@` (یعنی خود cusin.ir) | `YOUR_SERVER_IP` |
| A | `www` | `YOUR_SERVER_IP` |

صبر کنید تا DNS منتشر شود (معمولاً ۱۵ دقیقه تا چند ساعت برای .ir). تست:

```bash
ping -c 2 cusin.ir
```

باید آی‌پی سرور شما برگردد. **تا وقتی DNS درست نشده، سراغ مرحلهٔ SSL نروید.**

---

## ۴. فایروال

با کاربر root (یا sudo) روی سرور:

```bash
apt update && apt -y upgrade
apt -y install ufw
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP
ufw allow 443/tcp    # HTTPS
ufw enable
ufw status
```

> هیچ پورت دیگری (مخصوصاً 5432 پایگاه داده و 6379 ردیس) را باز نکنید —
> در فایل `docker-compose.prod.yml` هم این سرویس‌ها عمداً هیچ پورتی روی سرور
> باز نمی‌کنند.

**توصیهٔ اکید SSH:** ورود با رمز را ببندید و فقط با کلید وارد شوید
(`/etc/ssh/sshd_config` → `PasswordAuthentication no` و سپس `systemctl restart ssh`).

---

## ۵. نصب Docker

```bash
curl -fsSL https://get.docker.com | sh
docker --version
docker compose version
```

---

## ۶. دریافت پروژه

پروژه را در مسیر `/opt/cusin` قرار می‌دهیم:

```bash
mkdir -p /opt/cusin && cd /opt/cusin
git clone https://github.com/Mmziii/CusinGallery.git
cd CusinGallery
```

اگر روی سرور `git` نیست: `apt -y install git`. اگر دسترسی به GitHub از سرور
ممکن نیست، می‌توانید ZIP مخزن را روی کامپیوتر خود دانلود و با `scp` به سرور
منتقل و در `/opt/cusin/CusinGallery` باز کنید.

---

## ۷. ساخت فایل .env

همهٔ تنظیمات در **یک فایل** به نام `.env` در ریشهٔ پروژه است. این فایل هرگز
در گیت ذخیره نمی‌شود (در `.gitignore` است) — پس **از آن نسخهٔ پشتیبان جداگانه
نگه دارید**.

```bash
cd /opt/cusin/CusinGallery
cp .env.example .env
nano .env
```

توضیح متغیرها (همان ترتیب فایل):

| متغیر | چه بگذارید |
|---|---|
| `DJANGO_SETTINGS_MODULE` | همان `config.settings.production` بماند |
| `SECRET_KEY` | یک عبارت تصادفی بلند. تولید: `docker run --rm python:3.12-slim python -c "import secrets;print(secrets.token_urlsafe(64))"` — اگر `#` داشت داخل `"..."` بگذارید |
| `ALLOWED_HOSTS` | `cusin.ir,www.cusin.ir` |
| `CSRF_TRUSTED_ORIGINS` | `https://cusin.ir,https://www.cusin.ir` |
| `CORS_ALLOWED_ORIGINS` | `https://cusin.ir,https://www.cusin.ir` |
| `FRONTEND_URL` | `https://cusin.ir` |
| `POSTGRES_DB` / `POSTGRES_USER` | همان مقادیر نمونه قابل نگهداری است |
| `POSTGRES_PASSWORD` | **حتماً عوض شود** — یک رمز قوی تصادفی (دستور تولید بالا) |
| `EMAIL_HOST` و بقیهٔ EMAIL_* | مشخصات SMTP سرویس ایمیل‌تان (اختیاری ولی توصیه‌شده؛ بدون آن ایمیل‌های بازیابی رمز و اعلان سفارش ارسال نمی‌شوند) |
| `PAYMENT_GATEWAY` | `zarinpal` (گذاشتن `mock` در production ممکن نیست — برنامه بالا نمی‌آید) |
| `PAYMENT_MERCHANT_ID` | کد پذیرندهٔ زرین‌پال (بخش ۱۲). برای شروعِ آزمایشی: هر متن ۳۶ کاراکتری |
| `PAYMENT_ZARINPAL_SANDBOX` | برای تست اولیه `True`؛ **روز افتتاح حتماً `False`** |
| `PAYMENT_CALLBACK_URL` | `https://cusin.ir/payment/callback/` |
| `SMS_ENABLED` | `True` (یا `False` اگر فعلاً پیامک نمی‌خواهید) |
| `SMS_PROVIDER` | `kavenegar` (مقدار `console` در production مجاز نیست) |
| `KAVENEGAR_API_KEY` | کلید API پنل کاوه‌نگار (بخش ۱۳) |
| `SMS_SENDER` | شمارهٔ خط ارسال کاوه‌نگار (برای پیامک مستقیم) |
| `SMS_TEMPLATE_*` | نام قالب‌های تأییدشدهٔ پنل کاوه‌نگار؛ خالی = متن آمادهٔ خود سیستم |
| `OWNER_ALERT_PHONES` / `OWNER_ALERT_EMAILS` | شماره/ایمیل خودتان برای دریافت هشدار «سفارش جدید پرداخت شد» و «موجودی کم» (جداشده با کاما؛ خالی = آن کانال خاموش) |
| `LOW_STOCK_THRESHOLD` | آستانهٔ هشدار موجودی کم (پیش‌فرض ۳) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | اختیاری — ارسال هشدارهای مالک به تلگرام؛ هر دو لازم است وگرنه کانال خاموش می‌ماند (تلگرام از سرورهای ایرانی ممکن است فیلتر/ناپایدار باشد) |
| `BALE_BOT_TOKEN` / `BALE_CHAT_ID` | اختیاری — همین قابلیت در پیام‌رسان بله (پیش‌فرض داخلی؛ آدرس `https://tapi.bale.ai/business/bot<TOKEN>/sendMessage`) |
| `ADMIN_2FA_REQUIRED` | در production پیش‌فرض `True` است؛ ورود به پنل مدیریت با کد یک‌بارمصرف اپلیکیشن (بخش ۲۲). غیرفعال‌سازی صریح = خطای FAIL در `check_production` |
| `HTTPS_ENABLED` | تا وقتی SSL نگرفته‌اید `False`؛ بعد از بخش ۹ → `True` |
| `ADMIN_URL` | آدرس پنل مدیریت. پیش‌فرض `admin/` است ولی ربات‌ها مدام آن را اسکن می‌کنند؛ یک مقدار خصوصی بگذارید (مثلاً `panel-cusin-88`) و بک‌اند را ری‌استارت کنید — پنل در `https://cusin.ir/panel-cusin-88/` باز می‌شود |
| `SENTRY_DSN` | اختیاری — DSN پروژهٔ رایگان sentry.io برای دریافت خطاها (بک‌اند؛ خطاهای فرانت هم از همین مسیر ثبت می‌شوند — سطر بعدی) |
| `VITE_SENTRY_DSN` | اختیاری، در `frontend/.env` — هر مقدار غیرخالی = فعال‌شدن گزارش خطاهای فرانت‌اند (خرابی صفحه در ErrorBoundary به `POST /api/v1/site/report-error/` ارسال و با همین `SENTRY_DSN` بک‌اند ثبت می‌شود). خالی = مرورگر هیچ چیزی نمی‌فرستد. بعد از تغییر، build فرانت لازم است |
| `LOG_FORMAT` | `json` بماند (لاگ ساختاریافته برای `docker compose logs`) |
| `VITE_SITE_ORIGIN` | `https://cusin.ir` (برای لینک‌های سئو) |
| بقیه (هزینهٔ ارسال، `ORDER_EXPIRY_HOURS` و…) | پیش‌فرض‌ها منطقی‌اند؛ هر وقت خواستید عوض کنید |

---

## ۸. اولین استقرار

```bash
cd /opt/cusin/CusinGallery

# چون هنوز گواهی SSL نداریم، nginx را با پیکربندی موقت HTTP بالا می‌آوریم
# (توضیح کامل در بخش ۹). ابتدا فقط اجزای غیر-nginx:
docker compose -f docker-compose.prod.yml up -d --build db redis backend scheduler frontend

# صبر کنید تا backend سالم بالا بیاید (migrate و collectstatic خودکار است):
docker compose -f docker-compose.prod.yml logs -f backend
# اولین خط‌ها باید بگویند: applying database migrations ... starting gunicorn

# ساخت حساب مدیر پنل:
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser

# بازسازی فهرست جستجوی نرمال‌شدهٔ محصولات (Part R5 — جستجوی فارسی):
# این دستور تکرارپذیر (idempotent) و بی‌خطر است؛ یک‌بار بعد از اعمال
# مایگریشن‌ها اجرا شود تا محصولاتِ از قبل موجود هم متن جستجوی نرمال‌شده
# بگیرند. محصولات جدید هنگام ذخیره خودشان به‌روز می‌شوند و تغییر نام
# برند/دسته هم به‌صورت خودکار در جستجو منتشر می‌شود.
docker compose -f docker-compose.prod.yml exec backend python manage.py backfill_search_text
```

حالا با `http://YOUR_SERVER_IP/admin/` (موقتاً بدون دامنه/SSL) یا پس از بالا
آوردن nginx موقت (بخش ۹) با `http://cusin.ir/admin/` وارد پنل مدیریت شوید.

---

## ۹. فعال‌سازی SSL

گواهی رایگان Let's Encrypt با سرویس `certbot` که در compose تعریف شده گرفته و
**هر ۱۲ ساعت خودکار تمدید** می‌شود. مراحل دقیق (فقط اولین بار):

```bash
cd /opt/cusin/CusinGallery

# ۱) پیکربندی موقت HTTP را فعال و پیکربندی اصلی را موقتاً کنار بگذارید
cp nginx/prod.d/00-bootstrap-http.conf.example nginx/prod.d/00-bootstrap.conf
mv nginx/prod.d/cusin.conf nginx/prod.d/cusin.conf.pending

# ۲) nginx و certbot را بالا بیاورید
docker compose -f docker-compose.prod.yml up -d nginx certbot

# ۳) گواهی را صادر کنید (ایمیل واقعی خودتان را بگذارید)
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  -d cusin.ir -d www.cusin.ir \
  --email you@example.com --agree-tos --no-eff-email

# ۴) به پیکربندی اصلی (HTTPS) برگردید
rm nginx/prod.d/00-bootstrap.conf
mv nginx/prod.d/cusin.conf.pending nginx/prod.d/cusin.conf
docker compose -f docker-compose.prod.yml restart nginx

# ۵) به Django بگویید HTTPS فعال است
#    در فایل .env مقدار HTTPS_ENABLED=True شود، سپس:
docker compose -f docker-compose.prod.yml restart backend
```

تست: `https://cusin.ir` باید با قفل سبز باز شود و `http://cusin.ir` خودکار به
https برود — **بدون حلقهٔ ریدایرکت** (Django هدر `X-Forwarded-Proto` را از
nginx می‌گیرد و ریدایرکت تکراری نمی‌کند). آدرس بازگشت پرداخت
`https://cusin.ir/payment/callback/` هم همین‌جا توسط nginx به بک‌اند می‌رسد.

> **تمدید گواهی:** خودکار انجام می‌شود. برای اینکه nginx گواهیِ تمدیدشده را
> بدون قطعی بارگذاری کند، این cron هفتگی را اضافه کنید (`nginx -s reload`
> هیچ قطعی ایجاد نمی‌کند):
>
> ```bash
> crontab -e
> # این خط را اضافه کنید (دوشنبه‌ها ساعت ۴ بامداد):
> 0 4 * * 1 cd /opt/cusin/CusinGallery && docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload
> ```

---

## ۱۰. گواهی سلامت استقرار

یک ابزار داخلی همهٔ تنظیمات حیاتی را چک می‌کند و فهرست PASS/WARN/FAIL
(فارسی و انگلیسی) می‌دهد:

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py check_production
```

هر `[FAIL]` یعنی سایت آماده نیست — همان متنِ راهنما را دنبال کنید. هر `[WARN]`
را جدی بگیرید (مخصوصاً هشدار روشن‌بودن سندباکس زرین‌پال). همچنین:

```bash
curl https://cusin.ir/healthz        # باید {"status": "ok", ...} بدهد
curl https://cusin.ir/robots.txt
curl https://cusin.ir/sitemap.xml | head
```

### پیش‌نمایش لینک در واتس‌اپ/تلگرام/اینستاگرام (متادیتای مخصوص خزنده‌ها)

خزنده‌های شبکه‌های اجتماعی و پیام‌رسان‌ها (واتس‌اپ، تلگرام، اینستاگرام، ایتا،
توییتر/ایکس، اسلک، لینکدین، دیسکورد و…) جاوااسکریپت اجرا **نمی‌کنند**؛ پس
متادیتایی که برنامهٔ React در مرورگر می‌نویسد را هرگز نمی‌بینند. به همین دلیل
پیکربندی nginx (هم `nginx/conf.d/cusin.conf` و هم `nginx/prod.d/cusin.conf`)
بر اساس User-Agent تشخیص می‌دهد که درخواست از یک خزنده است و برای دو دسته آدرس
آن را به بک‌اند (Django) می‌فرستد:

| آدرس سایت | پاسخ به خزنده |
|---|---|
| `/products/<slug>/` | `/seo/product/<slug>/` |
| `/shop/?category=<slug>` | `/seo/shop/?category=<slug>` |

این دو نقطهٔ پایانی یک سند HTML کوچک برمی‌گردانند: عنوان، توضیح، canonical،
تگ‌های `og:type/title/description/url/image`، کارت توییتر، دادهٔ ساخت‌یافتهٔ
JSON-LD محصول (قیمت و موجودی) و یک لینک به صفحهٔ واقعی. تصویر با بزرگ‌ترین
نسخهٔ WebP موجود (۱۲۰۰ ← ۸۰۰ ← ۴۰۰) و در نبود تصویر با
`/brand/og-placeholder.png` پر می‌شود. محصول یا دستهٔ **غیرفعال/ناموجود** همیشه
۴۰۴ می‌گیرد تا هیچ‌وقت پیش‌نمایش کالای منتشرنشده بیرون نرود. پاسخ‌ها ۵ دقیقه
(`Cache-Control: public, max-age=300`) کش می‌شوند.

بازدیدکنندهٔ عادی هیچ تغییری نمی‌بیند: همان اپلیکیشن React سرو می‌شود.

آزمایش دستی (با User-Agent یک خزنده):

```bash
curl -A "WhatsApp/2.23" https://cusin.ir/products/<slug>/ | head -30
curl -A "TelegramBot (like TwitterBot)" "https://cusin.ir/shop/?category=<slug>" | head -30
curl -A "Mozilla/5.0" https://cusin.ir/products/<slug>/ | head -5   # همان SPA
```

نکتهٔ استقرار: این بلوک‌ها به `map $http_user_agent` نیاز دارند که در همان
فایل‌های `conf.d` تعریف شده است؛ اگر فایل را جای دیگری کپی می‌کنید، بلوک
`map` را هم با خودش ببرید. پس از تغییر، `docker compose -f
docker-compose.prod.yml restart nginx` و بعد همان `curl`های بالا را اجرا کنید.

---

## ۱۱. اضافه‌کردن محصولات

همهٔ کارها از پنل مدیریت (`https://cusin.ir/admin/`):

- **یکی‌یکی:** منوی «محصولات» ← «افزودن» (تصویر، قیمت به تومان، موجودی،
  دسته‌بندی و برند را از قبل بسازید).
- **دسته‌جمعی:** منوی «محصولات» ← «واردکردن از فایل» (CSV/Excel) — راهنمای
  ستون‌ها در `docs/OWNER_GUIDE.fa.md` بخش ۵.
- **دادهٔ نمایشی:** فقط برای دیدن ظاهر سایت:
  `docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo`
  (بعداً از پنل پاکشان کنید).

صفحات «دربارهٔ ما / تماس / ارسال و مرجوعی / قوانین / حریم خصوصی» در frontend
متن **نمونه** دارند: فایل‌های `frontend/src/pages/info/*.jsx` را با متن واقعی
خودتان عوض کنید (یا از پشتیبان فنی بخواهید) و سپس image را دوباره بسازید
(بخش ۱۶). نشانهٔ e-namad هم در `frontend/src/components/Footer.jsx` جای
مشخص دارد.

---

## ۱۲. زرین‌پال: از آزمایشی به واقعی

**مرحلهٔ آزمایشی (قبل از افتتاح — توصیه می‌شود):**
`PAYMENT_ZARINPAL_SANDBOX=True` و `PAYMENT_MERCHANT_ID` با هر مقدار
۳۶ کاراکتری. یک سفارش کامل بزنید و صفحهٔ سندباکس زرین‌پال را ببینید.

**مرحلهٔ واقعی:**

1. در [زرین‌پال](https://www.zarinpal.com/) حساب پذیرنده بسازید و درگاه را
   فعال کنید (احراز هویت صنفی/اینماد لازم دارد).
2. «کد پذیرنده» (Merchant ID) را از پنل بردارید → در `.env` داخل
   `PAYMENT_MERCHANT_ID`.
3. در تنظیمات درگاهِ پنل زرین‌پال، **آدرس بازگشت** را دقیقاً
   `https://cusin.ir/payment/callback/` ثبت کنید.
4. در `.env`: `PAYMENT_ZARINPAL_SANDBOX=False`.
5. `docker compose -f docker-compose.prod.yml restart backend`
6. یک خرید **واقعی** کوچک انجام دهید و در پنل زرین‌پال ببینید؛ سپس همان
   سفارش را در پنل مدیریت لغو کنید تا جریان «بازپرداخت وجه» (بخش ۸
   OWNER_GUIDE) را هم تمرین کرده باشید.

---

## ۱۳. تنظیم پیامک (کاوه‌نگار)

1. در [کاوه‌نگار](https://panel.kavenegar.com/) حساب بسازید و اعتبار شارژ کنید.
2. از «تنظیمات ← API Key» کلید را بردارید → `KAVENEGAR_API_KEY` در `.env`.
3. یک **خط ارسال** (sender) بگیرید → `SMS_SENDER` (برای پیامک مستقیم لازم است).
4. (اختیاری) سه قالب آماده در پنل بسازید (بازیابی رمز / تأیید سفارش / ارسال
   سفارش) و نام‌شان را در `SMS_TEMPLATE_*` بگذارید؛ خالی بگذارید همان متن‌های
   آمادهٔ فارسی سیستم ارسال می‌شود.
5. `docker compose -f docker-compose.prod.yml restart backend` و یک بار
   «بازیابی رمز» با حساب فقط-موبایلی تست کنید. نتیجه در پنل مدیریت ←
   «گزارش اعلان‌ها» دیده می‌شود.

---

## ۱۴. عملیات روزمره

- **سفارش‌ها:** پنل مدیریت ← «سفارش‌ها» (راهنمای کامل: `docs/OWNER_GUIDE.fa.md`).
- **بازپرداخت‌ها:** فیلتر «وضعیت بازپرداخت وجه = نیازمند بازپرداخت» هر روز
  چک شود.
- **لاگ‌ها:**
  ```bash
  docker compose -f docker-compose.prod.yml logs -f backend     # API
  docker compose -f docker-compose.prod.yml logs scheduler      # کارهای زمان‌بندی‌شده
  docker compose -f docker-compose.prod.yml logs nginx
  ```
- **مانیتورینگ:** یک سرویس uptime (هر نمونهٔ رایگان) روی
  `https://cusin.ir/healthz` تنظیم کنید؛ خطاهای برنامه هم با `SENTRY_DSN`
  به ایمیل‌تان می‌آید.
- **کارهای خودکار سرویس `scheduler` (بدون دخالت شما):**
  - هر ساعت: لغو سفارش‌های پرداخت‌نشدهٔ رهاشده (`expire_unpaid_orders`).
  - هر ساعت: پیامک یادآور سبد خرید (`send_cart_reminders`) -- فقط اگر
    `CART_REMINDER_ENABLED=True` باشد (پیش‌فرض خاموش؛ بخش زیر را بخوانید).
  - روزانه: بازسازی جدول «کالاهایی که با هم خریده شده‌اند» از سفارش‌های
    پرداخت‌شده (`rebuild_frequently_bought_together`) -- خوراکِ بخش
    «پیشنهاد همراه» صفحهٔ محصول. اجرای دستی همان لحظه هم ممکن است:
    ```bash
    docker compose -f docker-compose.prod.yml exec backend \
      python manage.py rebuild_frequently_bought_together
    ```

### پیامک یادآور سبد خرید (اختیاری، پیش‌فرض خاموش)

این قابلیت به مشتریِ واردشده‌ای که سبدش را رها کرده، **یک** پیامک یادآوری
می‌فرستد -- فقط با رضایت صریح خود مشتری (گزینهٔ «پیامک تبلیغاتی» در صفحهٔ
حساب کاربری، پیش‌فرض خاموش).

**قبل از روشن‌کردن، حتماً با ارائه‌دهندهٔ پیامک (مثلاً کاوه‌نگار) هماهنگ کنید:**
ارسال پیامک تبلیغاتی/انبوه در ایران قانون و شرایط خودش را دارد (احراز هویت،
الگوی پیام، ساعات مجاز) و برخی خطوط سرویس‌دهنده اصلاً پیامک تبلیغاتی را
نمی‌رسانند. تا وقتی از ارائه‌دهنده تأیید نگرفته‌اید، این قابلیت را خاموش نگه دارید.

برای روشن‌کردن در `.env`:

```bash
CART_REMINDER_ENABLED=True        # پیش‌فرض: False
CART_REMINDER_AFTER_HOURS=24      # سبدی که این‌قدر ساعت دست‌نخورده مانده
CART_REMINDER_COOLDOWN_DAYS=7     # حداکثر یک پیامک در این بازه برای هر مشتری
```

قانون‌های خودکار (نیازی به تنظیم ندارند): فقط مشتریان دارای رضایت، هر «وضعیت
سبد» حداکثر یک‌بار، اگر بعد از رهاکردن سفارش داده باشند پیامکی نمی‌رود،
بین ساعت ۲۱ تا ۹ صبح (به وقت تهران) هیچ پیامکی ارسال نمی‌شود، متن پیامک شامل
راهنمای لغو است و همهٔ ارسال‌ها در گزارش اعلان‌ها ثبت می‌شوند.

---

## ۱۵. پشتیبان‌گیری

اسکریپت آماده: `scripts/backup.sh` — از پایگاه داده (فرمت فشردهٔ pg_dump) و
عکس‌ها/فایل‌های آپلودشده (media) نسخه می‌گیرد و خودکار نسخه‌های قدیمی‌تر از
۱۴ روز را پاک می‌کند. بکاپ‌ها در `/var/backups/cusin` ذخیره می‌شوند —
**هرگز داخل پوشهٔ پروژه/گیت ذخیره نکنید.**

cron روزانه:

```bash
sudo mkdir -p /var/backups/cusin && sudo chown "$USER" /var/backups/cusin
crontab -e
# این خط را اضافه کنید:
15 3 * * * cd /opt/cusin/CusinGallery && ./scripts/backup.sh >> /var/log/cusin-backup.log 2>&1
```

**قانون طلایی:** هفته‌ای یک‌بار پوشش بکاپ را به جای دیگری هم کپی کنید
(سرور دیگر، فضای ابری، یا حتی `scp` به کامپیوتر خودتان):

```bash
scp -r user@YOUR_SERVER_IP:/var/backups/cusin ~/cusin-backups/
```

---

## ۱۶. به‌روزرسانی سایت

```bash
cd /opt/cusin/CusinGallery
git fetch --tags
git checkout <tag-or-commit-جدید>          # یا git pull برای آخرین main
docker compose -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f backend   # migrate خودکار اجرا می‌شود
docker compose -f docker-compose.prod.yml exec backend python manage.py check_production
```

قطع سرویس معمولاً چند ثانیه است. متن صفحات اعلان‌دار (بخش ۱۱) را قبل از build
ویرایش کرده باشید.

---

## ۱۷. بازگشت به نسخهٔ قبل

اگر به‌روزرسانی خراب شد:

```bash
cd /opt/cusin/CusinGallery
git checkout <commit-قبلی>
docker compose -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.prod.yml up -d
```

> **مهم:** اگر نسخهٔ جدید migration اجرا کرده باشد، کدِ قدیمی ممکن است با
> دیتابیسِ جدید سازگار نباشد. در آن حالت یا رو به جلو اصلاح کنید (به
> پشتیبان فنی اطلاع دهید) یا از بکاپِ قبل از به‌روزرسانی restore کنید
> (بخش ۱۸). به همین دلیل **قبل از هر به‌روزرسانی** یک بکاپ دستی بگیرید:
> `./scripts/backup.sh`

---

## ۱۸. بازیابی از بکاپ

```bash
cd /opt/cusin/CusinGallery

# ۱) بکاپ دستی از وضعیت فعلی (احتیاط)
./scripts/backup.sh

# ۲) بازیابی پایگاه داده (+ فایل‌ها در صورت نیاز)
./scripts/restore.sh /var/backups/cusin/db/db-YYYYMMDD-HHMMSS.dump \
                     /var/backups/cusin/media/media-YYYYMMDD-HHMMSS.tar.gz

# ۳) ری‌استارت بک‌اند (migrationهای لازم دوباره اعمال می‌شوند)
docker compose -f docker-compose.prod.yml restart backend

# ۴) بررسی
curl https://cusin.ir/healthz
```

---

## ۱۹. چک‌لیست پیش از افتتاح

- [ ] `check_production` بدون هیچ `[FAIL]` اجرا شد (و WARNهای سندباکس/HTTPS جدی گرفته شدند).
- [ ] `https://cusin.ir` با قفل TLS باز می‌شود و `http://` به آن ریدایرکت می‌شود (بدون حلقه).
- [ ] `HTTPS_ENABLED=True` شده.
- [ ] **یک سفارش آزمایشی کامل با سندباکس زرین‌پال**: ثبت‌نام ← سبد ← کوپن ←
      پرداخت ← صفحهٔ نتیجهٔ فارسی ← «پرداخت شده» در پنل ← پیامک/ایمیل تأیید
      در «گزارش اعلان‌ها».
- [ ] **جریان بازپرداخت تمرین شد**: همان سفارش آزمایشی لغو شد ← 💸 ظاهر شد ←
      «بازپرداخت شده» با یادداشت ثبت شد.
- [ ] `PAYMENT_ZARINPAL_SANDBOX=False` شد و یک خرید واقعی کوچک انجام و در پنل
      زرین‌پال رؤیت شد (سپس لغو/بازپرداخت شد).
- [ ] پیامک واقعی تست شد (بازیابی رمز با حساب فقط-موبایلی).
- [ ] cron بکاپ فعال است و **یک restore کامل با موفقیت تمرین شد** (بخش ۱۸).
- [ ] بکاپ به خارج از سرور کپی شد.
- [ ] صفحه‌های درباره/تماس/قوانین/حریم خصوصی با متن واقعی جایگزین و نشان
      e-namad در فوتر اضافه شد.
- [ ] `/sitemap.xml` در Google Search Console ثبت شد.
- [ ] یک سرویس uptime روی `/healthz` فعال شد.

---

## ۲۰. خرابی‌های رایج

| علامت | علت احتمالی و راه‌حل |
|---|---|
| `backend` بالا نمی‌آید | `docker compose -f docker-compose.prod.yml logs backend` — معمولاً یک `RuntimeError` گویا است (SECRET_KEY خالی، PAYMENT_GATEWAY=mock، KAVENEGAR_API_KEY خالی…). همان را در `.env` درست کنید و `up -d` again. |
| سایت 502 می‌دهد | بک‌اند خوابیده است؛ لاگ بالا را ببینید. اگر DB نرسد: `docker compose ps` و `logs db`. |
| ریدایرکت بی‌پایان (ERR_TOO_MANY_REDIRECTS) | `HTTPS_ENABLED=True` است ولی nginx هدر `X-Forwarded-Proto` نمی‌فرستد — باید با همین فایل‌های `nginx/prod.d` بالا آمده باشید، نه پیکربندی دست‌ساز. |
| گواهی SSL کار نمی‌کند | فایل `nginx/prod.d/cusin.conf` باید active باشد (نه bootstrap) و volumeهای certbot در compose mounted باشند؛ `docker compose logs certbot`. |
| پیامک نمی‌رود | پنل مدیریت ← «گزارش اعلان‌ها» ← ردیف «ناموفق» و متن خطا (معمولاً اتمام اعتبار کاوه‌نگار). |
| پرداخت به سایت برنمی‌گردد | در پنل زرین‌پال آدرس بازگشت دقیقاً `https://cusin.ir/payment/callback/` ثبت شده؟ nginx همان مسیر را به backend می‌دهد (در `nginx/prod.d/cusin.conf` هست). |
| سفارش‌های پرداخت‌نشده تلنبار شده | سرویس `scheduler` باید هر ساعت اجرا شود: `docker compose logs scheduler`. |

---

## ۲۱. آنالیتیکس اختیاری (حریم‌خصوصی‌محور)

در `.env` دو متغیر اختیاری دارید: `ANALYTICS_SCRIPT_URL` و `ANALYTICS_SITE_ID`. هر دو
خالی بمانند، **هیچ اسکریپتی لود نمی‌شود** و کوکی‌ای ساخته نمی‌شود. اگر مقدار بدهید،
اسکریپت فقط در فروشگاه (SPA) لود می‌شود — پنل مدیریت و صفحهٔ بازگشت درگاه هرگز آن را
نمی‌آورند — و به «Do Not Track» مرورگر احترام می‌گذارد.

گزینه‌های پیشنهادی: **Plausible خودمیزبان** (سبک، بدون کوکی، سازگار با حریم خصوصی) یا
**Matomo خودمیزبان**. سرویس‌هایی مثل Google Analytics از داخل ایران اغلب ناپایگار یا
مسدودند و با تحریم‌های اسکریپت‌های خارجی برای بازدیدکنندگان ایرانی مشکل‌ساز می‌شوند؛
به همین دلیل پیش‌فرض این پروژه «خاموش» است. پس از تغییر متغیرها، image فرانت باید
دوباره build شود (متغیرهای VITE در زمان build جای‌گذاری می‌شوند):

```bash
docker compose -f docker-compose.prod.yml build frontend && \
docker compose -f docker-compose.prod.yml up -d
```

## ۲۲. تائید دومرحله‌ای پنل مدیریت (2FA)

در production ورود به پنل مدیریت علاوه بر نام‌کاربری/رمز، به یک **کد یک‌بارمصرف**
از اپلیکیشن authenticator (TOTP) نیاز دارد (`ADMIN_2FA_REQUIRED` در production به‌طور
پیش‌فرض روشن است و `manage.py check_production` در صورت غیرفعال‌شدنِ صریح، خطای FAIL می‌دهد).

### ثبت‌نام دستگاه برای یک کاربر (enroll)

```bash
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py enroll_admin_2fa <username>
```

خروجی سه چیز می‌دهد:
1. آدرس `otpauth://...` — همین آدرس را در اپلیکیشن authenticator کاربر
   (Google Authenticator، FreeOTP، Microsoft Authenticator و…) اسکن/وارد کنید؛
2. مسیر یک فایل **QR** (PNG) — برای اسکن راحت‌تر با گوشی؛
3. چند **کد پشتیبان یک‌بارمصرف** — هر کدام فقط یک بار کار می‌کند؛ جای امن نگه‌دارید
   (اگر گوشی گم شود و این کدها هم نباشند، فقط با دستور بازیابی زیر می‌توان وارد شد).

### بازیابی (گم‌شدن گوشی یا کدها)

```bash
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py reset_admin_2fa <username>     # حذف دستگاه‌ها
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py enroll_admin_2fa <username>    # ثبت‌نام دوباره
```

> مشتریان هیچ تأثیری نمی‌بینند؛ این لایه فقط برای ورود کارکنان به `/admin/` است.
> برای غیرفعال‌کردن (توصیه نمی‌شود) مقدار `ADMIN_2FA_REQUIRED=False` را در `.env`
> بگذارید و بک‌اند را ری‌استارت کنید.

---

## ۲۳. نصب روی شبکه های محدود (اینترنت کند یا آینه های مسدود)

ساخت ایمیج‌ها فقط در سه جا به اینترنت نیاز دارد. اگر هر کدام در شبکهٔ شما کند یا
مسدود بود، راه‌حل همان ستون سوم است — **هیچ آینه‌ای در پروژه هارد‌کد نشده** و
بدون تنظیم این متغیرها، همه‌چیز مثل قبل از سرویس‌های پیش‌فرض استفاده می‌کند:

| مرحله | از کجا دانلود می‌کند | اگر مسدود/کند بود |
|---|---|---|
| ایمیج‌های پایه (`python:3.12-slim`، `node:20-alpine`، `nginx:1.27-alpine`، `postgres:16-alpine`، `redis:7-alpine`) | Docker Hub | بخش ۲۳-۳ (پیش‌بارگیری) |
| وابستگی‌های پایتون (بک‌اند) | PyPI — فقط فایل wheel | بخش ۲۳-۱ (`PIP_INDEX_URL`) |
| وابستگی‌های Node (فرانت‌اند) | رجیستری npm | بخش ۲۳-۲ (`NPM_CONFIG_REGISTRY`) |

> **از این نسخه به بعد، ساخت ایمیج بک‌اند هیچ کاری با مخازن Debian ندارد.**
> قبلاً یک قدم `apt-get` برای نصب `libpq-dev` و `gcc` وجود داشت که روی شبکه‌های
> بدون دسترسی به `deb.debian.org` کل build را با خطای اتصال متوقف می‌کرد. آن قدم
> حذف شد، چون همهٔ وابستگی‌ها فایل wheel آمادهٔ پایتون ۳٫۱۲ دارند و
> `psycopg2-binary` خودش `libpq` را همراه دارد؛ یعنی نه کامپایلری لازم است و نه
> `libpq-dev`. اگر روزی پکیجی wheel نداشته باشد، build با پیام واضح متوقف می‌شود
> (پارامتر `--only-binary=:all:`) — نه با خطای گمراه‌کنندهٔ «کامپایلر پیدا نشد».

### ۲۳-۱. آینهٔ PyPI (بک‌اند)

```bash
# به‌جای <آدرس آینه> آدرس آینهٔ داخلی/شرکتی خودتان را بگذارید:
PIP_INDEX_URL=https://<آدرس آینه>/simple/ \
    docker compose -f docker-compose.prod.yml build backend
```

همین متغیر را می‌توانید یک‌بار در فایل `.env` کنار پروژه بگذارید تا همهٔ buildهای
بعدی از آن استفاده کنند. (روی کامپیوتر خودتان هم معادل آن `pip config set
global.index-url https://<آدرس آینه>/simple/` است.)

### ۲۳-۲. آینهٔ رجیستری npm (فرانت‌اند)

```bash
NPM_CONFIG_REGISTRY=https://<آدرس آینه>/ \
    docker compose -f docker-compose.prod.yml build frontend
```

بدون Docker (مثلاً روی ویندوز، بخش ۲۴) یک‌بار برای همیشه:

```bash
npm config set registry https://<آدرس آینه>/
npm config delete registry     # برگشت به رجیستری پیش‌فرض، هر وقت خواستید
```

> نام `NPM_CONFIG_REGISTRY` تصادفی نیست: خود npm هم همین متغیر محیطی را می‌خواند،
> پس اگر آینه را در محیط سرور تنظیم کرده باشید، build بدون هیچ پارامتر اضافه‌ای
> از آن استفاده می‌کند.

### ۲۳-۳. پیش‌بارگیری ایمیج‌های پایه (وقتی Docker Hub فیلتر است)

روی کامپیوتری که به Docker Hub دسترسی دارد، ایمیج‌ها را بگیرید و به‌صورت فایل به
سرور منتقل کنید:

```bash
# روی ماشین با دسترسی:
docker pull python:3.12-slim
docker pull node:20-alpine
docker pull nginx:1.27-alpine
docker pull postgres:16-alpine
docker pull redis:7-alpine
docker save python:3.12-slim node:20-alpine nginx:1.27-alpine \
           postgres:16-alpine redis:7-alpine -o cusin-base-images.tar

# فایل را به سرور کپی کنید (مثلاً با scp) و آنجا:
docker load -i cusin-base-images.tar
```

بعد از `docker load`، دستور `docker compose build` ایمیج‌های پایه را از حافظهٔ
محلی برمی‌دارد و دیگر سراغ Docker Hub نمی‌رود.

اگر سرور شما به یک **رجیستری آینه** دسترسی دارد، می‌توانید آن را در
`/etc/docker/daemon.json` معرفی کنید (نام/آدرس آینه را از ارائه‌دهندهٔ زیرساخت
خودتان بگیرید؛ این پروژه هیچ آینهٔ خاصی را پیشنهاد یا اجباری نمی‌کند):

```json
{ "registry-mirrors": ["https://<آدرس رجیستری آینه>"] }
```

```bash
systemctl restart docker
```

---

## ۲۴. اجرای فروشگاه روی کامپیوتر خودتان بدون Docker (ویندوز)

برای یک نگاه سریع به سایت، تغییر ظاهر، یا تست پنل مدیریت لازم نیست Docker نصب
کنید. این مسیر **فقط برای کار محلی** است: پایگاه داده SQLite می‌شود و سرور واقعی
همان Docker + PostgreSQL (بخش‌های ۵ تا ۸) باقی می‌ماند.

پیش‌نیازها:

| مورد | توضیح |
|---|---|
| Python 3.12 | **فقط همین نسخه** (۳٫۱۱ یا ۳٫۱۳ ممکن است با وابستگی‌های پین‌شده نخواند). از python.org نصب کنید و در نصب تیک **Add python.exe to PATH** را بزنید |
| Node.js نسخهٔ LTS | از nodejs.org (نسخهٔ LTS مثل ۲۲) — برای اجرای رابط کاربری |
| بدون PostgreSQL | لازم نیست؛ پایگاه داده یک فایل ساده (`db.sqlite3`) می‌شود |

مرحله ۱ — بک‌اند (پنجرهٔ اول ترمینال):

```bat
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=sqlite:///db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

اگر PowerShell استفاده می‌کنید، خط `set` را با این عوض کنید:

```powershell
$env:DATABASE_URL="sqlite:///db.sqlite3"
```

مرحله ۲ — رابط کاربری (پنجرهٔ دوم ترمینال؛ پنجرهٔ اول باید باز بماند):

```bat
cd frontend
npm ci
npm run dev
```

سپس در مرورگر `http://localhost:5173` را باز کنید (نه پورت ۸۰۰۰).

**چرا دو پورت؟** سرور توسعهٔ Vite روی پورت **۵۱۷۳** بالا می‌آید و درخواست‌های
`/api` و `/media` را خودش به بک‌اند روی پورت **۸۰۰۰** می‌فرستد
(`frontend/vite.config.js`). پس مرورگر فقط با ۵۱۷۳ حرف می‌زند و کوکی ورود/CSRF
روی یک دامنه می‌ماند؛ Django هم باید در همان پنجرهٔ اول در حال اجرا باشد.

نکته‌های کوچک:

- فایل `backend/db.sqlite3` در گیت ذخیره نمی‌شود (`*.sqlite3` در `.gitignore`).
  برای شروع از صفر کافی است همین فایل را پاک کنید و `python manage.py migrate`
  را دوباره بزنید.
- مجموعهٔ تست‌های خودکار را با همین تنظیم می‌توانید اجرا کنید
  (`python manage.py test`). طبق روال پروژه، مرجعِ رسمی **PostgreSQL** است؛ روی
  SQLite همهٔ ۸۷۶ تست سبز می‌شوند و فقط دو تست «هم‌زمانیِ پرداخت» خودشان رد
  می‌شوند (دلیلش در کد نوشته شده: SQLite کل فایل پایگاه داده را قفل می‌کند و
  قفل‌گذاری سطریِ PostgreSQL را نمی‌توان روی آن آزمود).
- پنل مدیریت: `http://localhost:8000/admin/` با همان کاربری که
  `createsuperuser` ساخته است.

*این راهنما همراه مخزن به‌روز می‌شود. تغییرات بزرگ هر فاز در `README.md` و
`docs/PAYMENTS.md` هم مستند شده‌اند.*
