/**
 * Browser-safe contracts shared by the data registration package and frontend.
 *
 * Keep each record shape aligned with its decorated runtime entity in
 * `@rayfin-app/data`. This package must stay isomorphic, so do not import the
 * decorated classes here.
 */
export interface DiagnosisRecord {
  id: string;
  title: string;
  notes: string;
  owner_id: string;
  tenant: string;
  period: string;
  feature: string;
  events: number;
  activeUsers: number;
  avgDuration?: number | null;
  previousEvents?: number | null;
  previousUsers?: number | null;
  capturedAt: Date | string;
}

export const ACTION_STATUSES = ['Planned', 'In progress', 'Done'] as const;
export const ACTION_PRIORITIES = ['Normal', 'High'] as const;
export type ActionStatus = (typeof ACTION_STATUSES)[number];
export type ActionPriority = (typeof ACTION_PRIORITIES)[number];

export interface FollowUpRecord {
  id: string;
  diagnosis_id: string;
  title: string;
  notes: string;
  owner_id: string;
  status: ActionStatus;
  priority: ActionPriority;
  dueDate: string;
  createdAt: Date | string;
  updatedAt: Date | string;
}

export type UniversalAppSchema = {
  Diagnosis: DiagnosisRecord;
  FollowUp: FollowUpRecord;
};
