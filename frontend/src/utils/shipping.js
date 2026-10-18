export const EXPRESS_UNAVAILABLE_MESSAGE = "ارسال اکسپرس فعلاً فقط برای شهر تهران";

const normalizedDestination = (value) => {
  const text = String(value ?? "").trim().replace(/\s+/g, " ").toLowerCase();
  // Match the backend's legacy alias, not an arbitrary substring.
  return text === "tehran" ? "تهران" : text;
};

export function isExpressEligible(province, city) {
  return normalizedDestination(province) === "تهران"
    && ["تهران", "شهرستان تهران"].includes(normalizedDestination(city));
}
