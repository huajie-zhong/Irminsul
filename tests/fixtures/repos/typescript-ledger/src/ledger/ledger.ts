const traced = (_value: unknown, _context: unknown): void => {};

const audit = (_label: string) => traced;

@traced
export class Ledger {
  limit = 500;
  ownerName = "";
  static format = (cents: number): string => (cents / 100).toFixed(2);

  get owner(): string {
    return this.ownerName;
  }

  set owner(name: string) {
    this.ownerName = name;
  }

  @audit("remove")
  // Recorded in the audit trail with the entry it removes.
  @traced
  remove(id: string): string {
    return `${this.ownerName}:${id}`;
  }
}

export interface Loan {
  title: string;
  daysOut(): number;
}

export enum Membership {
  Basic,
  Plus = 2,
}

export type Charge = {
  cents: number;
};
