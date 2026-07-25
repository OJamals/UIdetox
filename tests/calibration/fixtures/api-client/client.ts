export async function loadOrders() {
  return fetch("http://localhost:3000/orders");
}
