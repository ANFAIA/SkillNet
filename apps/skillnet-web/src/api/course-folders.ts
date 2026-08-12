import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'

export interface CourseFolder {
  id: string
  name: string
  course_count?: number
  created_at?: string
  updated_at?: string
}

export function useCourseFolders() {
  return useQuery({
    queryKey: ['course-folders'],
    queryFn: () => get<CourseFolder[]>('/course-folders'),
  })
}

export function useCreateCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => post<CourseFolder>('/course-folders', { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['course-folders'] }),
  })
}

export function useRenameCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      put<CourseFolder>(`/course-folders/${id}`, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-folders'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useDeleteCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<void>(`/course-folders/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-folders'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}
