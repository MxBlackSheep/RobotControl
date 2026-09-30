/** 24-hour clock time, as on the instrument PC ("14:30"). */
export const clockTime = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

/** "Today 14:30", "Tomorrow 09:00", "Wed 2 Oct 09:00", or "2 Oct 2025 09:00" in another year; an unreadable value is returned as given. */
export function dayTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((new Date(date).setHours(0, 0, 0, 0) - today.getTime()) / 86400000);
  const day = days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : days === -1 ? 'Yesterday'
    // UK day-month order ("Mon 28 Sep"), as used in the lab; the comma-free form fits list columns.
    : date.getFullYear() !== today.getFullYear() ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '');
  return `${day} ${clockTime(date)}`;
}
