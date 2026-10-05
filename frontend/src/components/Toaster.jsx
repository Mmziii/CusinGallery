import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { onToast } from "../utils/toast";

/**
 * Bottom-corner toast stack (Part 3). CSS-only slide/fade; honors
 * prefers-reduced-motion via the .toast transition rules in CSS.
 * Part S2 item 6: a toast may carry an optional router-link action
 * (e.g. «مشاهده سبد» right after add-to-cart).
 */
function Toaster() {
  const [items, setItems] = useState([]);

  useEffect(
    () =>
      onToast(({ message, kind, action }) => {
        const id = `${Date.now()}-${Math.random()}`;
        setItems((list) => [...list.slice(-3), { id, message, kind, action: action || null }]);
        setTimeout(() => {
          setItems((list) => list.filter((item) => item.id !== id));
        }, 4200);
      }),
    []
  );

  if (items.length === 0) return null;
  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast--${item.kind}`}>
          <span>{item.message}</span>
          {item.action ? (
            <Link className="toast__action" to={item.action.to}>
              {item.action.label}
            </Link>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default Toaster;
