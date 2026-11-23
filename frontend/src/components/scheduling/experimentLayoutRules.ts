import type { PlateAssignment, PlateLayout } from './ExperimentPlateGrid';

export type LayoutRule = {kind:'whole_count'; parameter:string; assignment:string};

// Parse decimal text as scaled integers, including JSON numbers written in exponent notation.
// Never multiply a binary floating-point fraction by the well count.
function decimal(value:string) {
  // Match the finite JSON number sent to the server, including .5 input and exponent form.
  if (!value.trim() || !Number.isFinite(Number(value))) return null;
  value = String(Number(value));
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(value.trim());
  if (!match) return null;
  const scale = (match[3]?.length ?? 0) - Number(match[4] ?? 0);
  const digits = BigInt(`${match[1]}${match[2]}${match[3] ?? ''}`);
  return {numerator:scale < 0 ? digits * 10n ** BigInt(-scale) : digits, scale:Math.max(0, scale)};
}
function formatDecimal(numerator:bigint, scale:number) {
  const sign = numerator < 0n ? '-' : '';
  const digits = (numerator < 0n ? -numerator : numerator).toString().padStart(scale + 1, '0');
  return sign + (scale ? `${digits.slice(0,-scale)}.${digits.slice(-scale)}`.replace(/\.?0+$/, '') : digits);
}
export function evaluateLayoutRule(rule:LayoutRule, value:string, layout:PlateLayout, assignments:PlateAssignment[]) {
  const count = Object.values(layout).filter(value => value === rule.assignment).length;
  const label = assignments.find(a => a.value === rule.assignment)?.label.toLowerCase() ?? rule.assignment;
  const fraction = decimal(value);
  if (!fraction) return {valid:false, reason:`Enter a valid ${rule.parameter}.`, kept:''};
  const numerator = BigInt(count) * fraction.numerator;
  const denominator = 10n ** BigInt(fraction.scale);
  const kept = formatDecimal(numerator, fraction.scale);
  const percent = formatDecimal(fraction.numerator * 100n, fraction.scale);
  return {valid:numerator % denominator === 0n, kept, reason:`${count} ${label}${count === 1 ? '' : 's'}: ${percent}% keeps ${kept} wells`};
}
