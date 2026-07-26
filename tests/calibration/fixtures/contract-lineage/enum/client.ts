import axios, { AxiosResponse } from "axios";

interface CreateUser {
  role: "admin" | "member";
}

interface User {
  id: string;
}

export async function createUser() {
  return axios.post<User, AxiosResponse<User>, CreateUser>("/users");
}
