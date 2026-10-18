import PropTypes from "prop-types";
import { useId, useState } from "react";

import { faDigits } from "../utils/faDigits";
import { normalizePersianText } from "../utils/persianText";
import { brandShape } from "../utils/shapes";

function BrandFilter({ brands, selected, onChange, locked = false }) {
  const [search, setSearch] = useState("");
  const name = useId();
  const query = normalizePersianText(search);
  const matches = brands.filter((brand) => normalizePersianText(brand.name).includes(query));
  return (
    <div className="brand-filter" role="group" aria-label="برند">
      <input
        type="search"
        placeholder="جستجوی برند…"
        aria-label="جستجوی برند"
        value={search}
        disabled={locked}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="brand-filter__options">
        {!locked ? (
          <label className="filter-option">
            <input type="radio" name={name} value="" checked={!selected} onChange={() => onChange("")} />
            همه برندها
          </label>
        ) : null}
        {matches.map((brand) => (
          <label className="filter-option" key={brand.id}>
            <input type="radio" name={name} value={brand.slug} checked={selected === brand.slug} disabled={locked} onChange={() => onChange(brand.slug)} />
            {faDigits(brand.name)}
          </label>
        ))}
        {!matches.length ? <p role="status" className="muted">موردی پیدا نشد</p> : null}
      </div>
    </div>
  );
}

BrandFilter.propTypes = {
  brands: PropTypes.arrayOf(brandShape).isRequired,
  selected: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  locked: PropTypes.bool,
};

export default BrandFilter;
