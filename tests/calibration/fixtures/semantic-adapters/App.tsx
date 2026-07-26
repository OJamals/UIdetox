import { useQuery } from "@tanstack/react-query";
import { useQuery as useApolloQuery } from "@apollo/client";
import ky from "ky";
import { fetchItems } from "./barrel";
import { useGetUsersQuery } from "./generated";
import { createClient } from "@acme/generated";

const generatedClient = createClient();

export function App() {
  useQuery({ queryKey: ["items"], queryFn: () => fetchItems("/api/items") });
  useApolloQuery(GET_ITEMS);
  useGetUsersQuery();
  generatedClient.users.list();
  ky.post("/api/events");
  return <main data-testid="application" />;
}
