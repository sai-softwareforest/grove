// A member is known by a short id: the part of the office email address
// before the "@", in lower case, or a badge number with its leading zeros removed.
export function memberId(input: string): string {
  const text = input.trim().toLowerCase();
  if (/^\d+$/.test(text)) return String(Number(text));
  return text.split("@")[0];
}
