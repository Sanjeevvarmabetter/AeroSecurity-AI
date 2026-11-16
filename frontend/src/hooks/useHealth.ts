import { useQuery } from "@tanstack/react-query";

import { getHealth } from "../services/api";

export const useHealth = () =>
  useQuery({ queryKey: ["system-health"], queryFn: getHealth, refetchInterval: 15_000 });
