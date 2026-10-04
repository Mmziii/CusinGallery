import InfoPageLayout from "./InfoPageLayout";

/**
 * ⚠ OWNER-EDITABLE PLACEHOLDER CONTENT — the privacy statement must
 * describe what THIS store actually collects and how it is used. Review
 * and adapt before launch, then set `placeholder={false}`. It already
 * reflects the technical reality of this codebase (session auth, no card
 * data stored, masked notification logs).
 */
function PrivacyPage() {
  return (
    <InfoPageLayout
      title="حریم خصوصی"
      path="/privacy/"
      description="سیاست حفظ حریم خصوصی و داده‌های کاربران در کازین گالری."
    >
      <p>
        <strong>[متن نمونه — منطبق بر وضعیت واقعی فروشگاه بازبینی شود]</strong>
      </p>
      <h2>چه داده‌هایی جمع‌آوری می‌شود؟</h2>
      <ul>
        <li>اطلاعات حساب: شمارهٔ موبایل، ایمیل (اختیاری) و نام.</li>
        <li>اطلاعات سفارش: آدرس و شمارهٔ تماس گیرنده، اقلام و مبالغ خرید.</li>
        <li>
          اطلاعات پرداخت نزد درگاه پرداخت معتبر (زرین‌پال) می‌ماند؛ <strong>شمارهٔ کامل
          کارت یا رمز شما هرگز در سیستم ما ذخیره نمی‌شود</strong> (فقط شمارهٔ مرجع تراکنش
          و شمارهٔ ماسک‌شدهٔ کارت).
        </li>
      </ul>
      <h2>داده‌ها چگونه استفاده می‌شوند؟</h2>
      <ul>
        <li>پردازش و ارسال سفارش‌ها، پشتیبانی و اطلاع‌رسانی وضعیت سفارش (پیامک/ایمیل).</li>
        <li>انجام تکالیف قانونی (مالیاتی و صنفی).</li>
      </ul>
      <h2>حقوق شما</h2>
      <p>
        می‌توانید برای مشاهده، اصلاح یا حذف اطلاعات حساب خود با پشتیبانی تماس بگیرید.
        کوکی‌های این سایت فقط برای نگهداری نشست ورود (session) استفاده می‌شوند.
      </p>
    </InfoPageLayout>
  );
}

export default PrivacyPage;
