import PropTypes from "prop-types";

import { usePageMeta } from "../../hooks/usePageMeta";

/**
 * Shared layout for the trust/policy pages (Phase E): about, contact,
 * shipping & returns, terms, privacy.
 *
 * ⚠ OWNER: the texts passed to this layout are PLACEHOLDERS. Replace the
 * content in each page file (frontend/src/pages/info/*.jsx) with the
 * store's real information BEFORE launch — see the pre-launch checklist
 * in docs/DEPLOY.md. The yellow notice below renders on purpose until
 * the owner removes it (delete the `placeholder` prop from the page).
 */
function OwnerEditNotice() {
  return (
    <div className="owner-edit-notice" role="note">
      ⚠ متن این صفحه <strong>نمونه (placeholder)</strong> است. مدیر فروشگاه باید آن را با
      اطلاعات واقعی جایگزین کند و سپس این اعلان را حذف نماید
      (پراپ <code dir="ltr">placeholder</code> در فایل همین صفحه).
    </div>
  );
}

function InfoPageLayout({ title, path, description, placeholder = true, children }) {
  usePageMeta({ title, path, description });
  return (
    <div className="container info-page">
      <h1>{title}</h1>
      {placeholder ? <OwnerEditNotice /> : null}
      <div className="info-page__body card">{children}</div>
    </div>
  );
}

InfoPageLayout.propTypes = {
  title: PropTypes.string.isRequired,
  path: PropTypes.string.isRequired,
  description: PropTypes.string,
  placeholder: PropTypes.bool,
  children: PropTypes.node.isRequired,
};

export default InfoPageLayout;
