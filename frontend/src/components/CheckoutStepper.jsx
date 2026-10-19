import PropTypes from "prop-types";
import { Link } from "react-router-dom";

export const CHECKOUT_STEPS = [
  { id: "cart", num: "۱", label: "سبد خرید", path: "/cart/" },
  { id: "delivery", num: "۲", label: "روش تحویل", path: "/checkout/?step=delivery" },
  { id: "address", num: "۳", label: "اطلاعات تحویل", path: "/checkout/?step=address" },
  { id: "review", num: "۴", label: "بازبینی و پرداخت", path: "/checkout/?step=review" },
];

export default function CheckoutStepper({ currentStep = "cart" }) {
  const currentIndex = CHECKOUT_STEPS.findIndex((s) => s.id === currentStep);
  const safeIndex = currentIndex >= 0 ? currentIndex : 0;

  return (
    <ol className="checkout__steps" aria-label="مراحل ثبت سفارش">
      {CHECKOUT_STEPS.map((step, index) => {
        const isDone = index < safeIndex;
        const isCurrent = index === safeIndex;
        const isTodo = index > safeIndex;

        const content = (
          <>
            <span className="checkout__step-num" aria-hidden="true">
              {step.num}
            </span>
            <span className="checkout__step-label">{step.label}</span>
          </>
        );

        return (
          <li
            key={step.id}
            className={`checkout__step ${isDone ? "checkout__step--done checkout__step--clickable" : ""} ${
              isCurrent ? "checkout__step--current" : ""
            } ${isTodo ? "checkout__step--todo" : ""}`}
            aria-current={isCurrent ? "step" : undefined}
          >
            {isDone ? (
              <Link to={step.path} className="checkout__step-link">
                {content}
              </Link>
            ) : (
              <span className="checkout__step-static">{content}</span>
            )}
            {index < CHECKOUT_STEPS.length - 1 && (
              <span className="checkout__step-separator" aria-hidden="true">
                ›
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

CheckoutStepper.propTypes = {
  currentStep: PropTypes.oneOf(["cart", "delivery", "address", "review"]).isRequired,
};
