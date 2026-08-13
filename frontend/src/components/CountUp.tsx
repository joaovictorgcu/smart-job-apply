import { useCountUp } from '@/hooks/useCountUp';
import { formatNumber } from '@/lib/format';

/** A display-only number that eases to its value (snaps under reduced motion). */
export function CountUp({ value }: { value: number }) {
  const animated = useCountUp(value);
  return <>{formatNumber(animated)}</>;
}
