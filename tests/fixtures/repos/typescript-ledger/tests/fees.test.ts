import { expect, test } from "vitest";

import { lateFee } from "../src/ledger/fees";

function chargeFor(days: number): number {
  return lateFee(days);
}

test("a payment within the grace period is free", () => {
  expect(chargeFor(1)).toBe(0);
});

test("a late payment is charged by the day", () => {
  expect(chargeFor(5)).toBe(125);
});
