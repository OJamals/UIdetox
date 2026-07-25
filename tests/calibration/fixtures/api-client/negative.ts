export async function loadOrders(baseUrl: string) {
  return fetch(`${baseUrl}/orders`);
}
