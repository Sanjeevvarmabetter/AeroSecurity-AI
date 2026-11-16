import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { correlateThreats, explainAnomaly, getAISettings, getAnalyses, investigateAircraft, putAISettings, type AiTarget } from "../services/api";
import { useToken } from "../stores/auth";

export const useAISettings = (check: boolean) => {
  const token = useToken();
  return useQuery({ queryKey: ["ai-settings", token, check], queryFn: () => getAISettings(check), enabled: !!token, staleTime: 30_000 });
};
export const useAnalyses = (q: { anomaly_id?: string; icao24?: string }) => {
  const token = useToken();
  return useQuery({ queryKey: ["analyses", token, q], queryFn: () => getAnalyses(q), enabled: !!token });
};
export const useRunAnalysis = (kind: "anomaly" | "aircraft" | "correlation", subject: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (t: AiTarget) =>
      kind === "anomaly" ? explainAnomaly(subject, t) : kind === "correlation" ? correlateThreats(subject, t) : investigateAircraft(subject, t),
    onSettled: () => qc.invalidateQueries({ queryKey: ["analyses"] }),
  });
};
export const useSaveAISettings = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: putAISettings, onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-settings"] }) });
};
