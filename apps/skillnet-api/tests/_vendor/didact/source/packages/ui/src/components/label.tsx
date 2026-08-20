import * as React from "react";
import { Label as LabelPrimitive } from "radix-ui";

import { cn } from "../lib/cn.js";

/**
 * Label -- an accessible form label, ported verbatim from the same reference kit as Button (see
 * button.tsx's header comment). Backed by `radix-ui`'s `Label.Root` (the unified `radix-ui`
 * package, same import style as Toggle/ToggleGroup), which forwards clicks to its associated
 * control and plays well with `htmlFor`/`id` association. Standard Tailwind utilities reading
 * `@didact/theme`'s tokens, the same `data-slot="label"` attribute, and the peer/group-disabled
 * styling from the reference. The only change from the reference source is the `cn` import path.
 */
function Label({
  className,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
