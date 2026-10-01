/** 24-hour clock time, as on the instrument PC ("14:30"). */
export const clockTime = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

// Fixed three-letter names: browser locale data varies ("Sept" in some en-GB builds) and would break list columns.
const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Today 14:30", "Tomorrow 09:00", "Wed 2 Oct 09:00", or "2 Oct 2025 09:00" in another year (UK day-month order); an unreadable value is returned as given. */
export function dayTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((new Date(date).setHours(0, 0, 0, 0) - today.getTime()) / 86400000);
  const day = days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : days === -1 ? 'Yesterday'
    : date.getFullYear() !== today.getFullYear() ? `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`
    : `${weekdays[date.getDay()]} ${date.getDate()} ${months[date.getMonth()]}`;
  return `${day} ${clockTime(date)}`;
}
