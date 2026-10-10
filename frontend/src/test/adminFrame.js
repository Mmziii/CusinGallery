/**
 * Test helper: run the REAL admin theme scripts (backend/static/admin_theme/js)
 * inside an isolated jsdom iframe.
 *
 * Each mount gets its own window and document, so document-level listeners
 * from one test cannot leak into the next. The scripts are read from disk and
 * evaluated in the iframe's realm, then DOMContentLoaded is dispatched exactly
 * as a browser would after parsing the page.
 */
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ADMIN_JS = path.resolve(HERE, "../../../backend/static/admin_theme/js");

export function readAdminScript(name) {
  return fs.readFileSync(path.join(ADMIN_JS, name), "utf8");
}

/**
 * Mount `bodyHtml` in a fresh iframe, install stubs jsdom lacks, evaluate the
 * given scripts in the iframe and fire DOMContentLoaded.
 *
 * @param {string} bodyHtml  markup for <body>
 * @param {string[]} scripts  script sources (see readAdminScript)
 * @param {{fetch?: Function}} options
 */
export function mountAdminPage(bodyHtml, scripts, options = {}) {
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const win = iframe.contentWindow;
  const doc = win.document;
  doc.open();
  // Base URL = the iframe's own document URL, so fragment links resolve to
  // same-document targets and jsdom can record them as hash navigations.
  doc.write(
    '<!doctype html><html lang="fa" dir="rtl"><head><base href="about:blank"></head><body></body></html>'
  );
  doc.close();
  doc.body.innerHTML = bodyHtml;

  // jsdom does not implement layout-driven scrolling.
  win.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {
    win.__scrolled = (win.__scrolled || []).concat(this);
  };
  if (options.fetch) win.fetch = options.fetch;

  for (const source of scripts) win.eval(source);
  doc.dispatchEvent(new win.Event("DOMContentLoaded"));

  return {
    win,
    doc,
    cleanup() {
      iframe.remove();
    },
  };
}

/** Build a minimal fetch Response-like object for the palette tests. */
export function jsonResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}
