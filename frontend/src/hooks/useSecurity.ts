import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addNote,
  getAnomalies,
  getAnomaly,
  getAnomalyStats,
  getEmergencies,
  getInvestigations,
  getMe,
  setStatus,
  startInvestigation,
  type AnomalyQuery,
} from "../services/api";
import { useToken } from "../stores/auth";
import type { WorkflowStatus } from "../types/anomaly";

export const useMe = () => {
  const token = useToken();
  return useQuery({ queryKey: ["me", token], queryFn: getMe, enabled: !!token, staleTime: 60_000 });
};
export const useAnomalies = (q: AnomalyQuery) => {
  const token = useToken();
  return useQuery({ queryKey: ["anomalies", token, q], queryFn: () => getAnomalies(q), enabled: !!token, placeholderData: keepPreviousData });
};
export const useAnomalyStats = () => {
  const token = useToken();
  return useQuery({ queryKey: ["anomaly-stats", token], queryFn: getAnomalyStats, enabled: !!token });
};
export const useAnomaly = (id: string | undefined) => {
  const token = useToken();
  return useQuery({ queryKey: ["anomaly", token, id], queryFn: () => getAnomaly(id!), enabled: !!token && !!id });
};
export const useEmergencies = (q: { squawk?: string; status?: string[] }) => {
  const token = useToken();
  return useQuery({ queryKey: ["emergencies", token, q], queryFn: () => getEmergencies({ ...q, limit: 100 }), enabled: !!token, refetchInterval: 30_000 });
};
export const useInvestigations = (status?: string[]) => {
  const token = useToken();
  return useQuery({ queryKey: ["investigations", token, status], queryFn: () => getInvestigations({ status, limit: 100 }), enabled: !!token });
};

/** Every workflow mutation refreshes all views that display anomaly state. */
function useRefresh() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["anomaly", "anomalies", "anomaly-stats", "emergencies", "investigations"]) qc.invalidateQueries({ queryKey: [key] });
  };
}
export const useStartInvestigation = (id: string) => {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (v: { note: string; name?: string }) => startInvestigation(id, v.note, v.name), onSuccess: refresh });
};
export const useSetStatus = (id: string) => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (v: { status: WorkflowStatus; reason: string; name?: string }) => setStatus(id, v.status, v.reason, v.name),
    onSuccess: refresh,
  });
};
export const useAddNote = (id: string) => {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (v: { body: string; name?: string }) => addNote(id, v.body, v.name), onSuccess: refresh });
};
