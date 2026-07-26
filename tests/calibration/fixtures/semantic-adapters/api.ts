import axios from "axios";

const client = axios.create();

export const request = (path: string) => client.get(path);
