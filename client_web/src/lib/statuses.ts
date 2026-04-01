import schema from '../../../shared/schema.yaml';

export type TaskStatus = string;

export const STATUSES: TaskStatus[] = schema.statuses.map((s: { id: string }) => s.id);

export const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  schema.statuses.map((s: { id: string; label: string }) => [s.id, s.label])
);

export const TRANSITIONS: Record<string, string[]> = schema.transitions;

export const TRANSITION_CONDITIONS: Record<string, unknown> = schema.transition_conditions;
