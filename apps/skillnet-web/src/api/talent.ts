import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { EnrollmentStatus, Paginated, UserSkillRead } from '../types'

export interface TalentPersonSummary {
  user_id: string
  full_name: string
  email: string
  assigned_count: number
  in_progress_count: number
  completed_count: number
  skill_count: number
  last_activity_at: string | null
}

export interface TalentCourseProgress {
  course_id: string
  title: string
  status: EnrollmentStatus
  progress: number | null
  started_at: string | null
  completed_at: string | null
}

export interface TalentSkill extends UserSkillRead {
  source_courses: TalentCourseProgress[]
}

export interface TalentPersonDetail {
  user_id: string
  full_name: string
  email: string
  courses: TalentCourseProgress[]
  skills: TalentSkill[]
}

export interface TalentSkillSummary {
  skill_id: string
  name: string
  description: string | null
  people_count: number
  course_count: number
}

export interface TalentCourseSummary {
  course_id: string
  title: string
  assigned_count: number
  in_progress_count: number
  completed_count: number
  skills: string[]
}

export interface TalentPeopleFilters {
  search?: string
  course_id?: string
  skill_id?: string
  status?: 'assigned' | 'in_progress' | 'completed'
}

function peopleQuery(filters: TalentPeopleFilters): string {
  const params = new URLSearchParams({ offset: '0', limit: '100' })
  if (filters.search?.trim()) params.set('search', filters.search.trim())
  if (filters.course_id) params.set('course_id', filters.course_id)
  if (filters.skill_id) params.set('skill_id', filters.skill_id)
  if (filters.status) params.set('status', filters.status)
  return params.toString()
}

export function useTalentPeople(filters: TalentPeopleFilters = {}) {
  return useQuery({
    queryKey: ['talent', 'people', filters],
    queryFn: () => get<Paginated<TalentPersonSummary>>(`/talent/people?${peopleQuery(filters)}`),
  })
}

export function useTalentPerson(userId?: string) {
  return useQuery({
    queryKey: ['talent', 'people', userId],
    queryFn: () => get<TalentPersonDetail>(`/talent/people/${userId}`),
    enabled: !!userId,
  })
}

export function useTalentSkills() {
  return useQuery({
    queryKey: ['talent', 'skills'],
    queryFn: () => get<TalentSkillSummary[]>('/talent/skills'),
  })
}

export function useTalentCourses() {
  return useQuery({
    queryKey: ['talent', 'courses'],
    queryFn: () => get<TalentCourseSummary[]>('/talent/courses'),
  })
}
