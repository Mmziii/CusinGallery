import InfoPageLayout from "./InfoPageLayout";

/**
 * ⚠ OWNER-EDITABLE PLACEHOLDER CONTENT — this page states the store's
 * legal shipping/return promises. Make it match reality (costs, windows,
 * conditions) before launch, then set `placeholder={false}`. The numbers
 * below mirror the DEFAULT env settings (shipping costs/delivery windows
 * in .env) — if you change one, change the other.
 */
function ShippingReturnsPage() {
  return (
    <InfoPageLayout
      title="رویهٔ ارسال و مرجوعی"
      path="/shipping-returns/"
      description="شرایط ارسال، هزینه‌ها، بازهٔ تحویل و رویهٔ مرجوع کردن کالا در کوزین گالری."
    >
      <h2>ارسال</h2>
      <ul>
        <li>
          [متن نمونه — مطابق تنظیمات واقعی] ارسال <strong>استاندارد</strong>: معمولاً ۳ تا ۵
          روز کاری، با هزینهٔ ثابت (ارسال رایگان برای خریدهای بالای مبلغ تعیین‌شده).
        </li>
        <li>
          [متن نمونه] ارسال <strong>اکسپرس</strong>: معمولاً ۱ تا ۲ روز کاری با هزینهٔ جداگانه.
        </li>
        <li>
          ظروف شکستنی با بسته‌بندی محافظ ارسال می‌شوند؛ لطفاً هنگام تحویل، سلامت بسته را
          بررسی کنید.
        </li>
      </ul>
      <h2>مرجوعی</h2>
      <ul>
        <li>
          [متن نمونه] در صورت انصراف از خرید، تا ۷ روز پس از تحویل امکان درخواست مرجوعی
          وجود دارد؛ کالا باید استفاده‌نشده و در بسته‌بندی اولیه باشد.
        </li>
        <li>
          [متن نمونه] کالای آسیب‌دیده یا مغایر با سفارش را حداکثر تا ۴۸ ساعت پس از تحویل
          اطلاع دهید تا بدون هزینه تعویض یا بازپرداخت شود.
        </li>
        <li>
          بازپرداخت مبالغ پس از رسیدن کالا و تأیید کارشناس، از همان مسیر پرداخت انجام
          می‌شود و معمولاً چند روز کاری زمان می‌برد.
        </li>
      </ul>
      <p>
        برای شروع درخواست مرجوعی با پشتیبانی تماس بگیرید (صفحهٔ «تماس با ما»)؛  شمارهٔ سفارش
        را همراه داشته باشید.
      </p>
    </InfoPageLayout>
  );
}

export default ShippingReturnsPage;
