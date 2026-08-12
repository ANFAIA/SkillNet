import * as React from "react";
import { Progress as ProgressPrimitive } from "radix-ui";

import { cn } from "../lib/cn.js";

export interface ProgressProps
  extends React.ComponentProps<typeof ProgressPrimitive.Root> {
  /** Classes applied to the moving indicator rather than the track. */
  indicatorClassName?: string;
}

/**
 * Progress -- a neutral determinate/indeterminate progress primitive. Radix owns progressbar ARIA;
 * the indicator is a purely visual reinforcement and callers must provide an accessible name.
 */
function Progress({ className, indicatorClassName, value, max = 100, ...props }: ProgressProps) {
  const safeMax = Number.isFinite(max) && max > 0 ? max : 100;
  const safeValue = value == null ? null : Math.max(0, Math.min(safeMax, value));
  const percent = safeValue == null ? 0 : (safeValue / safeMax) * 100;

  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={safeValue}
      max={safeMax}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-secondary", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        data-indeterminate={safeValue == null ? "true" : undefined}
        className={cn(
          "h-full w-full flex-1 bg-primary transition-transform duration-300 motion-reduce:transition-none data-[indeterminate=true]:opacity-40",
          indicatorClassName,
        )}
        style={{ transform: `translateX(-${100 - percent}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress };
