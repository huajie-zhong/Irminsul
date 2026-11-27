import { lateFee } from "./fees.js";

export const LateNotice = ({ days }: { days: number }) => (
  <p>Fee for {days} days late: {lateFee(days)} cents.</p>
);
