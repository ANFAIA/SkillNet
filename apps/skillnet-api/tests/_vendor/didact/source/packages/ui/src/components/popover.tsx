import * as React from "react";
import { Popover as PopoverPrimitive } from "radix-ui";

import { cn } from "../lib/cn.js";

/**
 * Popover -- an anchored, non-modal surface for compact supplementary content. Radix owns
 * positioning, collision avoidance, focus restoration, Escape and outside-click dismissal;
 * Didact adds the neutral token-driven surface and the shared focus/motion conventions.
 */
function Popover(props: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />;
}

function PopoverTrigger(props: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

function PopoverAnchor(props: React.ComponentProps<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" {...props} />;
}

function PopoverContent({
  className,
  align = "center",
  sideOffset = 6,
  collisionPadding = 8,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(
          "z-50 w-72 max-w-[calc(100vw-1rem)] rounded-lg border bg-popover p-4 text-popover-foreground outline-none transition-opacity duration-150 data-[state=closed]:opacity-0 data-[state=open]:opacity-100 motion-reduce:transition-none",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverAnchor, PopoverContent, PopoverTrigger };
