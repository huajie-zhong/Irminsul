import { rates } from "./rates";

export const GRACE_DAYS = 2;

const MAX_FEE = 500;

const waived = (days: number): boolean => days <= GRACE_DAYS;

export function lateFee(days: number): number {
  if (waived(days)) {
    return 0;
  }
  // The fee grows by the daily rate and stops at the cap.
  const charged = days * rates.daily;
  return Math.min(charged, MAX_FEE);
}

export function lateDays(input: string): number;
export function lateDays(input: number): number;
export function lateDays(input: string | number): number {
  return Number(input);
}
