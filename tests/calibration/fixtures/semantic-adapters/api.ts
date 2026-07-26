import axios, { type AxiosResponse } from "axios";

const client = axios.create();

export function request<TRequest, TResponse>(path: string, body: TRequest) {
  return client.post<TResponse, AxiosResponse<TResponse>, TRequest>(path, body);
}
