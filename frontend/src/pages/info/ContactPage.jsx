import InfoPageLayout from "./InfoPageLayout";

/**
 * ⚠ OWNER-EDITABLE PLACEHOLDER CONTENT — put the store's REAL contact
 * details here before launch (phone, email, address, hours), then set
 * `placeholder={false}`.
 */
function ContactPage() {
  return (
    <InfoPageLayout
      title="تماس با ما"
      path="/contact/"
      description="راه‌های ارتباطی با کوزین گالری: تلفن، ایمیل، آدرس و ساعات پاسخگویی."
    >
      <p><strong>[شمارهٔ تماس واقعی فروشگاه را وارد کنید]</strong></p>
      <dl className="info-page__facts">
        <div><dt>تلفن پشتیبانی</dt><dd dir="ltr">+98 21 0000 0000</dd></div>
        <div><dt>ایمیل</dt><dd dir="ltr">support@cusin.ir</dd></div>
        <div><dt>آدرس</dt><dd>[آدرس واقعی فروشگاه/انبار را وارد کنید]</dd></div>
        <div><dt>ساعات پاسخگویی</dt><dd>[مثلاً: شنبه تا چهارشنبه ۹ تا ۱۷]</dd></div>
      </dl>
      <p>
        برای پیگیری سفارش، از بخش <strong>حساب کاربری ← سفارش‌ها</strong> وضعیت و کد رهگیری
        مرسوله را مشاهده کنید؛ در صورت نیاز به پشتیبانی، شمارهٔ سفارش را همراه داشته باشید.
      </p>
    </InfoPageLayout>
  );
}

export default ContactPage;
