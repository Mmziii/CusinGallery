# تست سرتاسری (E2E) با Playwright — کازین گالری

این پوشه آزمون‌های مرورگر واقعی برای فروشگاه و پنل مدیریت را نگه می‌دارد. این آزمون‌ها عمداً جزو `npm test` (آزمون‌های Vitest) یا `manage.py test` نیستند؛ به سرور در حال اجرا و مرورگر Chromium نیاز دارند.

## نصب ابزار مرورگر

وابستگی Playwright جدا از وابستگی‌های Vite نگه داشته شده است:

```bash
cd e2e
npm ci
npx playwright install chromium   # فقط بار اول
```

## اجرای فروشگاه

ترمینال اول — بک‌اند Django با درگاه آزمایشی و پیامک کنسولی:

```bash
cd backend
export DJANGO_SETTINGS_MODULE=config.settings.development
export PAYMENT_GATEWAY=mock SMS_ENABLED=False
export POSTGRES_HOST=... POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000
```

ترمینال دوم — فرانت‌اند و پراکسی `/api` به بک‌اند:

```bash
cd frontend
npm install
npm run dev
```

اجرای جریان‌های فروشگاه (صفحهٔ اصلی، سبد مهمان، ثبت‌نام، سه روش ارسال و پرداخت mock):

```bash
cd e2e
E2E_BASE_URL=http://localhost:5173 npm test -- --project=chromium
```

برای آزمون کد تخفیف، `E2E_COUPON` را با کد فعال تنظیم کنید. بدون آن، فقط گام کد تخفیف رد می‌شود. این آزمون یک حساب تازه با شمارهٔ آزمایشی می‌سازد؛ از پایگاه‌دادهٔ توسعه استفاده کنید، نه دادهٔ مشتریان واقعی.

پروفایل‌های دستگاه موبایلِ فروشگاه نیز در کانفیگ موجودند:

```bash
cd e2e
E2E_BASE_URL=http://localhost:5173 npx playwright test --project=mobile-pixel

آزمون موبایل (Audit 19) — اندازه‌گیری واقعی گرید دو ستونه، سرریز افقی، نوار چسبان
فیلتر/مرتب‌سازی، مرحلهٔ «روش ارسال» در تسویه‌حساب موبایل و چرخهٔ رمز عبور:

```bash
cd e2e
E2E_BASE_URL=http://localhost:5173 npx playwright test mobile-grid.spec.js --project=chromium
```

بررسی ۴۰۴ واقعی فقط روی پشتهٔ کامل (nginx + Django) معنا دارد؛ برای آن:

```bash
E2E_BASE_URL=https://cusin.ir E2E_EXPECT_REAL_404=1 npx playwright test mobile-grid.spec.js --project=chromium
```
E2E_BASE_URL=http://localhost:5173 npx playwright test --project=mobile-iphone
```

## آزمون پنل مدیریت

این آزمون‌ها مستقیماً به بک‌اند متصل می‌شوند و نشست کاربر مدیر می‌خواهند. پیش از اجرا، `E2E_BASE_URL`، `E2E_ADMIN_USER` و `E2E_ADMIN_PASSWORD` را در محیط محلی تنظیم کنید؛ گذرواژه را در مخزن یا فایل‌های پروژه ننویسید. پایگاه‌داده باید دست‌کم یک ردیف در هر فهرست محصول، دسته‌بندی، سفارش، کاربر، کوپن و نظر داشته باشد؛ داشبورد دست‌کم چهار سفارش و آزمون‌های فرم یک سفارش قابل‌ویرایش می‌خواهند. آزمون تصویری بهتر است با محصولات، گونه‌ها و سفارش‌های نمونه اجرا شود.

```bash
cd e2e
E2E_BASE_URL=http://localhost:8000 \
E2E_ADMIN_USER=<نام-کاربری-مدیر> \
E2E_ADMIN_PASSWORD=<گذرواژه-محلی> \
npm run test:admin
```

برای استفاده از نسخهٔ Chromium ازپیش‌نصب‌شده به‌جای مرورگر دانلودشدهٔ Playwright، مسیر اجرایی را با `E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium` تنظیم کنید.

`e2e/admin-layout.spec.js` در عرض‌های ۳۲۰، ۳۷۵، ۱۰۲۴، ۱۲۸۰ و ۱۴۴۰ پیکسل، داشبورد و هر شش فهرست محصول، دسته‌بندی، سفارش، کاربر، کوپن و نظر را می‌سنجد. در ۱۲۸۰ و ۱۴۴۰ پیکسل، عرض همهٔ ستون‌ها و دیده‌شدن کنش‌های هر ردیف را بررسی می‌کند؛ در ۱۰۲۴ پیکسل نیز سرریز افقی را در جعبهٔ نتایج نگه می‌دارد. آزمون جداگانهٔ اعداد ۹رقمی در فهرست محصولات در ۱۲۸۰، ۱۴۴۰ و ۱۹۲۰ پیکسل اجرا می‌شود و فهرست برندها و بنرها را هم بررسی می‌کند. فرم‌های ویرایش محصول و سفارش را در همان عرض‌ها می‌سنجد و سرریز صفحه، اندازه و کنتراست متن، منوها، بستن با Escape و بازگرداندن فوکوس، منوی کناری موبایل و ظاهر روشن زیر شبیه‌سازی حالت تیرهٔ سیستم‌عامل را پوشش می‌دهد.

برای گرفتن تصاویر بازبینی در `e2e/screenshots/`، متغیر `E2E_CAPTURE_SCREENSHOTS=1` را اضافه کنید:

```bash
cd e2e
E2E_BASE_URL=http://localhost:8000 \
E2E_ADMIN_USER=<نام-کاربری-مدیر> \
E2E_ADMIN_PASSWORD=<گذرواژه-محلی> \
E2E_CAPTURE_SCREENSHOTS=1 \
npm run test:admin
```

تصاویر شامل داشبورد، فهرست‌ها و فرم‌های محصول و سفارش در اندازه‌های ۱۲۸۰ و ۳۷۵ پیکسل، منوهای اقدام گروهی/فیلتر/کاربر و منوی کناری موبایل‌اند. اجرای تصویری این تغییر در Chromium واقعی با دادهٔ نمونه انجام شده و ۸۰ آزمون پنل مدیریت با موفقیت گذشتند. فایل‌های PNG همین پوشه برای بازبینی در درخواست ادغام نگه داشته شده‌اند.
