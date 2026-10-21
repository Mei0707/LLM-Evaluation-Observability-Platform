import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
export const useData = <T>(key: string, path: string, poll = false) =>
  useQuery({
    queryKey: [key],
    queryFn: () => api<T>(path),
    refetchInterval: poll ? 2000 : false,
  });
