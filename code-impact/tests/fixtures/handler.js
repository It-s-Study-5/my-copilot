// handler.js
import { createOrder } from "./order.js";
export function handleOrderRequest(req) {
  return createOrder(req.price, req.quantity);
}
