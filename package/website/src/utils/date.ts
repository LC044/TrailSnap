export const parseDateRange = (text: string): { start: string, end: string, label: string } | null => {
  const t = text.trim();
  
  // YYYY
  let match = t.match(/^(\d{4})年?$/);
  if (match) {
    return { start: `${match[1]}-01-01T00:00:00Z`, end: `${match[1]}-12-31T23:59:59Z`, label: `${match[1]}年` };
  }
  // YYYY-MM or YYYY年MM月
  match = t.match(/^(\d{4})[-年](\d{1,2})月?$/);
  if (match) {
    const y = match[1];
    const m = match[2].padStart(2, '0');
    // Get last day of month
    const lastDay = new Date(parseInt(y), parseInt(m), 0).getDate();
    return { start: `${y}-${m}-01T00:00:00Z`, end: `${y}-${m}-${lastDay}T23:59:59Z`, label: `${y}年${m}月` };
  }
  // YYYY-MM-DD or YYYY年MM月DD日
  match = t.match(/^(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日号]?$/);
  if (match) {
    const y = match[1];
    const m = match[2].padStart(2, '0');
    const d = match[3].padStart(2, '0');
    return { start: `${y}-${m}-${d}T00:00:00Z`, end: `${y}-${m}-${d}T23:59:59Z`, label: `${y}年${m}月${d}日` };
  }
  return null;
}