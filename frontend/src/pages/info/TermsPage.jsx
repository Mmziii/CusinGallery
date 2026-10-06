import InfoPageLayout from "./InfoPageLayout";

/**
 * NOTE: OWNER-EDITABLE PLACEHOLDER CONTENT — terms of sale are a LEGAL
 * text. Replace this placeholder with terms reviewed for your business
 * (ideally by a lawyer) before launch, then set `placeholder={false}`.
 */
function TermsPage() {
  return (
    <InfoPageLayout
      title="شرایط و قوانین استفاده"
      path="/terms/"
      description="شرایط و قوانین خرید و استفاده از فروشگاه اینترنتی کازین گالری."
    >
      <p>
        <strong>[متن نمونه — پیش از راه‌اندازی با متن حقوقی واقعی جایگزین شود]</strong>
      </p>
      <h2>۱. کلیات</h2>
      <p>
        استفاده از وب‌سایت کازین گالری و ثبت سفارش، به معنای پذیرش شرایط زیر است. این
        شرایط ممکن است به‌روزرسانی شود؛ نسخهٔ معتبر، همین صفحه در زمان خرید است.
      </p>
      <h2>۲. حساب کاربری</h2>
      <p>
        اطلاعات حساب (شمارهٔ موبایل/ایمیل و رمز عبور) محرمانه است و مسئولیت حفظ آن و
        فعالیت‌های انجام‌شده با حساب، بر عهدهٔ کاربر است.
      </p>
      <h2>۳. سفارش و پرداخت</h2>
      <p>
        قیمت‌ها به تومان و شامل مالیات بر ارزش افزوده (در صورت اعمال) است. سفارش پس از
        پرداخت موفق ثبت قطعی می‌شود؛ تا پیش از پرداخت، امکان لغو سفارش وجود دارد.
      </p>
      <h2>۴. مسئولیت</h2>
      <p>
        [متن نمونه] مسئولیت فروشگاه در قبال هر سفارش حداکثر معادل مبلغ همان سفارش است و
        این شرایط هیچ‌گاه حقوق قانونی غیرقابل‌اسقاط مصرف‌کننده را محدود نمی‌کند.
      </p>
    </InfoPageLayout>
  );
}

export default TermsPage;
