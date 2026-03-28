export type TaskStatus = 'NEW' | 'STARTED' | 'BLOCKED' | 'WAITING_FOR_COMMAND_EXECUTION' | 'DONE' | 'NOT_REPRODUCIBLE' | 'CANCELLED';

export const STATUSES: TaskStatus[] = [
  'NEW', 'STARTED', 'BLOCKED', 'WAITING_FOR_COMMAND_EXECUTION', 'DONE', 'NOT_REPRODUCIBLE', 'CANCELLED'
];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  'NEW': 'New',
  'STARTED': 'Started',
  'BLOCKED': 'Blocked',
  'WAITING_FOR_COMMAND_EXECUTION': 'Waiting for Exec',
  'DONE': 'Done',
  'NOT_REPRODUCIBLE': 'Not Reproducible',
  'CANCELLED': 'Cancelled',
};
