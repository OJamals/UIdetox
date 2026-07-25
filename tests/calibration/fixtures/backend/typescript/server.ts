export type Order = { id: string };

export function listOrders(): Order[] {
  return [{ id: "order-1" }];
}
