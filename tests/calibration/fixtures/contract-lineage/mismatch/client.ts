import axios, { AxiosResponse } from "axios";

interface CreateUser {
  email: number;
}

interface User {
  id: string;
}

export async function createUser() {
  const result = await axios.post<User, AxiosResponse<User>, CreateUser>("/users");
  queryClient.invalidateQueries({ queryKey: ["users"] });
  return result.data;
}
