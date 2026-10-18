import PropTypes from "prop-types";
import { useEffect, useId, useMemo, useState } from "react";

import { mainGroups } from "../utils/categories";
import { faDigits } from "../utils/faDigits";
import { categoryShape } from "../utils/shapes";
import Icon from "./Icon";

/** Flat API rows retain their ordering; missing parents remain browseable. */
function buildTree(categories) {
  const byId = new Map(categories.map((category) => [category.id, category.slug]));
  const bySlug = new Map(categories.map((category) => [category.slug, { ...category, children: [] }]));
  const roots = [];
  for (const category of categories) {
    const node = bySlug.get(category.slug);
    const parent = bySlug.get(category.parent_slug || byId.get(category.parent));
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }
  return mainGroups(roots);
}

function includesSelection(category, selected, seen = new Set()) {
  if (seen.has(category.slug)) return false;
  seen.add(category.slug);
  return category.slug === selected || category.children.some((child) => includesSelection(child, selected, seen));
}

function CategoryNode({ category, selected, onChange, name, ancestors = [] }) {
  const hasSelection = includesSelection(category, selected);
  const [expanded, setExpanded] = useState(hasSelection);
  const listId = useId();
  useEffect(() => { if (hasSelection) setExpanded(true); }, [hasSelection]);
  // Corrupt imported parent chains must never recurse forever.
  if (ancestors.includes(category.slug)) return null;
  const children = category.children.filter((child) => !ancestors.includes(child.slug));
  return (
    <li>
      <div className="category-filter__row">
        <label className="filter-option">
          <input type="radio" name={name} value={category.slug} checked={selected === category.slug} onChange={() => onChange(category.slug)} />
          {faDigits(category.name)}
        </label>
        {children.length ? (
          <button
            type="button"
            className="category-filter__toggle"
            aria-label={`زیردسته‌های ${faDigits(category.name)}`}
            aria-expanded={expanded}
            aria-controls={listId}
            onClick={() => setExpanded((value) => !value)}
          >
            <Icon name="chevron-down" size={16} />
          </button>
        ) : null}
      </div>
      {children.length ? (
        <ul id={listId} hidden={!expanded}>
          {children.map((child) => (
            <CategoryNode key={child.slug} category={child} selected={selected} onChange={onChange} name={name} ancestors={[...ancestors, category.slug]} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function CategoryFilterTree({ categories, selected, onChange }) {
  const roots = useMemo(() => buildTree(categories), [categories]);
  const name = useId();
  return (
    <div className="category-filter" role="group" aria-label="دسته‌بندی">
      <label className="filter-option">
        <input type="radio" name={name} value="" checked={!selected} onChange={() => onChange("")} />
        همه دسته‌ها
      </label>
      <ul>
        {roots.map((category) => <CategoryNode key={category.slug} category={category} selected={selected} onChange={onChange} name={name} />)}
      </ul>
    </div>
  );
}

CategoryNode.propTypes = {
  category: categoryShape.isRequired,
  selected: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  name: PropTypes.string.isRequired,
  ancestors: PropTypes.arrayOf(PropTypes.string),
};
CategoryFilterTree.propTypes = {
  categories: PropTypes.arrayOf(categoryShape).isRequired,
  selected: PropTypes.string,
  onChange: PropTypes.func.isRequired,
};

export default CategoryFilterTree;
