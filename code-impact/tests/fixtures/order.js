// order.js
import { calculatePrice } from "./price.js";
export function createOrder(price, quantity) {
  const amount = calculatePrice(price, quantity);
  if (amount <= 0) {
    throw new Error("Invalid amount");
  }
  return saveOrder(amount);
}
