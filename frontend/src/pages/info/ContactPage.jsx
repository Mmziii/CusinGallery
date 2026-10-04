import useSiteSettings from "../../hooks/useSiteSettings";
import InfoPageLayout from "./InfoPageLayout";

/**
 * ⚠ OWNER: contact details now come from «تنظیمات فروشگاه» in the admin
 * panel (SiteSettings) -- edit them THERE, not in this file. Anything
 * still marked [متن نمونه] below is placeholder copy to replace (then
 * set `placeholder={false}`).
 */
function ContactPage() {
  const settings = useSiteSettings();

  return (
    <InfoPageLayout
      title="تماس با ما"
      path="/contact/"
      description="راه‌های ارتباطی با کازین گالری: تلفن، واتس‌اپ، تلگرام، اینستاگرام، نشانی و ساعات پاسخگویی."
    >
      <dl className="info-page__facts">
        {settings.phone ? (
          <div><dt>تلفن پشتیبانی</dt><dd dir="ltr">{settings.phone}</dd></div>
        ) : null}
        {settings.whatsapp ? (
          <div>
            <dt>واتس‌اپ</dt>
            <dd><a dir="ltr" href={`https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`}>{settings.whatsapp}</a></dd>
          </div>
        ) : null}
        {settings.telegram ? (
          <div>
            <dt>تلگرام</dt>
            <dd>
              <a
                dir="ltr"
                href={settings.telegram.startsWith("http") ? settings.telegram : `https://t.me/${settings.telegram.replace("@", "")}`}
              >
                {settings.telegram}
              </a>
            </dd>
          </div>
        ) : null}
        {settings.instagram ? (
          <div>
            <dt>اینستاگرام</dt>
            <dd>
              <a
                dir="ltr"
                href={settings.instagram.startsWith("http") ? settings.instagram : `https://instagram.com/${settings.instagram.replace("@", "")}`}
              >
                {settings.instagram}
              </a>
            </dd>
          </div>
        ) : null}
        {settings.address ? (
          <div><dt>نشانی</dt><dd>{settings.address}</dd></div>
        ) : null}
        {settings.working_hours ? (
          <div><dt>ساعات پاسخگویی</dt><dd>{settings.working_hours}</dd></div>
        ) : null}
      </dl>
      <p>
        ایمیل پشتیبانی: <span dir="ltr">support@cusin.ir</span> {/* [متن نمونه: ایمیل واقعی] */}
      </p>
      <p>
        برای پیگیری سفارش، از بخش <strong>حساب کاربری ← سفارش‌ها</strong> وضعیت و کد رهگیری
        مرسوله را مشاهده کنید؛ در صورت نیاز به پشتیبانی، شمارهٔ سفارش را همراه داشته باشید.
      </p>
    </InfoPageLayout>
  );
}

export default ContactPage;
