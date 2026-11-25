export function unused() {
  calculatePrice(10, 2);
}
export function ternary(price, quantity) {
  const amount = calculatePrice(price, quantity);
  return amount > 0 ? amount : 0;
}
export function method(price, quantity) {
  const amount = calculatePrice(price, quantity);
  return amount.toFixed();
}

function calculatePrice(price, quantity) {
  return price * quantity;
}
