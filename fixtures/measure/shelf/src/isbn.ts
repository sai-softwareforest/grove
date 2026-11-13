// ISBN handling: clean the input, convert ISBN-10 and verify the check digit.

export function clean(input: string): string {
  return input.replace(/[\s-]/g, "");
}

export function checkDigit13(first12: string): number {
  let sum = 0;
  for (let i = 0; i < 12; i++) {
    sum += Number(first12[i]) * (i % 2 === 0 ? 1 : 3);
  }
  return (10 - (sum % 10)) % 10;
}

export function toIsbn13(input: string): string {
  const digits = clean(input);
  if (digits.length === 10) {
    const body = "978" + digits.slice(0, 9);
    return body + checkDigit13(body);
  }
  if (digits.length !== 13 || !/^\d+$/.test(digits)) {
    throw new Error(`not an ISBN: ${input}`);
  }
  if (checkDigit13(digits.slice(0, 12)) !== Number(digits[12])) {
    throw new Error(`wrong check digit: ${input}`);
  }
  return digits;
}
