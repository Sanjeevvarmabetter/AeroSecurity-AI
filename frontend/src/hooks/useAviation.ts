import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getAircraft, getDataSources, getHistory, getLive, getTrajectory, searchAircraft } from "../services/api";
import { useToken } from "../stores/auth";

export interface Range {
  start?: string;
  end?: string;
  gap_s?: number;
}

// Queries are keyed by token so signing in/out refetches; none run without a token.
export const useAircraftSearch = (q: string) => {
  const token = useToken();
  return useQuery({ queryKey: ["aircraft", token, q], queryFn: () => searchAircraft(q), enabled: !!token, placeholderData: keepPreviousData });
};
export const useAircraft = (icao24: string | undefined) => {
  const token = useToken();
  return useQuery({ queryKey: ["aircraft", token, icao24], queryFn: () => getAircraft(icao24!), enabled: !!token && !!icao24 });
};
export const useHistory = (icao24: string | undefined, range: Range, offset: number) => {
  const token = useToken();
  return useQuery({
    queryKey: ["history", token, icao24, range, offset],
    queryFn: () => getHistory(icao24!, { ...range, limit: 50, offset }),
    enabled: !!token && !!icao24,
    placeholderData: keepPreviousData,
  });
};
export const useTrajectory = (icao24: string | undefined, range: Range) => {
  const token = useToken();
  return useQuery({ queryKey: ["trajectory", token, icao24, range], queryFn: () => getTrajectory(icao24!, range), enabled: !!token && !!icao24 });
};
export const useLive = (p: Parameters<typeof getLive>[0], refetchMs: number | false) => {
  const token = useToken();
  return useQuery({ queryKey: ["live", token, p], queryFn: () => getLive(p), enabled: !!token, refetchInterval: refetchMs, placeholderData: keepPreviousData });
};
export const useDataSources = () => {
  const token = useToken();
  return useQuery({ queryKey: ["data-sources", token], queryFn: getDataSources, enabled: !!token, refetchInterval: 30_000 });
};
