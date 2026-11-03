import type { Run } from '@personal-agent/sdk';

export const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const SKILL_NAMES: Record<string, string> = {
  'weekly-report': '周报生成',
  'document-summary': '文档总结',
};

export function isActive(run?: Run | null): run is Run {
  return !!run && ['queued', 'running'].includes(run.status);
}

export function skillDisplayName(name: string): string {
  return SKILL_NAMES[name] ?? name;
}

export function errorMessage(error: unknown): string {
  return (error as Error).message;
}
