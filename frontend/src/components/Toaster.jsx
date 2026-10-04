import { useEffect, useState } from "react";

import { onToast } from "../utils/toast";

/**
 * Bottom-corner toast stack (Part 3). CSS-only slide/fade; honors
 * prefers-reduced-motion via the .toast transition rules in CSS.
 */
function Toaster() {
  const [items, setItems] = useState([]);

  useEffect(
    () =>
      onToast(({ message, kind }) => {
        const id = `${Date.now()}-${Math.random()}`;
        setItems((list) => [...list.slice(-3), { id, message, kind }]);
        setTimeout(() => {
          setItems((list) => list.filter((item) => item.id !== id));
        }, 3800);
      }),
    []
  );

  if (items.length === 0) return null;
  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast--${item.kind}`}>
          {item.message}
        </div>
      ))}
    </div>
  );
}

export default Toaster;
