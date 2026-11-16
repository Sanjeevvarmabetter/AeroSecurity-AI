import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addIntel, correlateThreats, createReport, getConversation, getConversations, getIntel, getReport, getReports, importArxiv, sendChat,
  type AiTarget,
} from "../services/api";
import { useToken } from "../stores/auth";

export const useConversations = () => {
  const token = useToken();
  return useQuery({ queryKey: ["conversations", token], queryFn: getConversations, enabled: !!token });
};
export const useConversation = (id: string | null) => {
  const token = useToken();
  return useQuery({ queryKey: ["conversation", token, id], queryFn: () => getConversation(id!), enabled: !!token && !!id });
};
export const useSendChat = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { message: string; conversation_id: string | null; target: AiTarget }) => sendChat(v.message, v.conversation_id, v.target),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
};
export const useCorrelate = (anomalyId: string) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (t: AiTarget) => correlateThreats(anomalyId, t), onSettled: () => qc.invalidateQueries({ queryKey: ["analyses"] }) });
};
export const useIntel = (q: string) => {
  const token = useToken();
  return useQuery({ queryKey: ["intel", token, q], queryFn: () => getIntel(q), enabled: !!token });
};
export const useImportArxiv = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (v: { query: string; max: number }) => importArxiv(v.query, v.max), onSuccess: () => qc.invalidateQueries({ queryKey: ["intel"] }) });
};
export const useAddIntel = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addIntel, onSuccess: () => qc.invalidateQueries({ queryKey: ["intel"] }) });
};
export const useReports = () => {
  const token = useToken();
  return useQuery({ queryKey: ["reports", token], queryFn: getReports, enabled: !!token });
};
export const useReport = (id: number | null) => {
  const token = useToken();
  return useQuery({ queryKey: ["report", token, id], queryFn: () => getReport(id!), enabled: !!token && id !== null });
};
export const useCreateReport = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { subject: { anomaly_id?: string; icao24?: string }; includeAi: boolean }) => createReport(v.subject, v.includeAi),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
};
