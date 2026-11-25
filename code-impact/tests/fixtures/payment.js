// payment.js
import { calculatePrice } from "./price.js";
export function preparePayment(price, quantity) {
  return calculatePrice(price, quantity);
}
