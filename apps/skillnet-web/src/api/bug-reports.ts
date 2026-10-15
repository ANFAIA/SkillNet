import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { BugReport, BugReportAdmin, BugReportCreate } from '../types'

/** A report shared with the team can still be under review for a few seconds. */
const STILL_REVIEWING_MS = 5_000

export function useMyBugReports() {
  return useQuery({
    queryKey: ['bug-reports', 'mine'],
    queryFn: () => get<BugReport[]>('/bugs/mine'),
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === 'pending') ? STILL_REVIEWING_MS : false,
  })
}

export function useReportBug() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: BugReportCreate) => post<{ id: string; status: string }>('/bugs', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bug-reports'] }),
  })
}

export function useAdminBugReports() {
  return useQuery({
    queryKey: ['bug-reports', 'all'],
    queryFn: () => get<BugReportAdmin[]>('/bugs'),
  })
}

export function useFileBugReport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => post<BugReportAdmin>(`/bugs/${id}/file`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bug-reports'] }),
  })
}

export function useDiscardBugReport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => post<BugReportAdmin>(`/bugs/${id}/discard`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bug-reports'] }),
  })
}
