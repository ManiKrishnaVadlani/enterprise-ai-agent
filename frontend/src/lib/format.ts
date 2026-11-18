export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

export function formatRelative(value: string): string {
  const date = new Date(value); if (Number.isNaN(date.getTime())) return value;
  const diff = Date.now() - date.getTime(); const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "Just now"; if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24); return days < 7 ? `${days}d ago` : formatDate(value);
}
