import * as React from "react";
import { Separator as SeparatorPrimitive } from "radix-ui";

import { cn } from "../lib/cn.js";

/**
 * Separator -- a thin visual/semantic divider, ported verbatim from the same reference kit as
 * Button (see button.tsx's header comment). Backed by the accessible-primitives layer
 * (`radix-ui`'s `Separator`) rather than a bare `<hr>`/`<div>`: Radix's `Root` sets
 * `role="separator"` (or `none` when `decorative`) and `aria-orientation` for us, so a screen
 * reader gets the right semantics without this component having to reimplement them.
 */

function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
