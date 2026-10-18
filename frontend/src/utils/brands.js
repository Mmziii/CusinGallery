/** Slugs may contain Persian characters; never encode the whole path. */
export function brandUrl(slug) {
  return `/brands/${encodeURIComponent(slug)}/`;
}
