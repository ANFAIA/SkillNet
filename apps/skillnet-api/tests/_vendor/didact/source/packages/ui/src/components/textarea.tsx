import * as React from "react";

import { cn } from "../lib/cn.js";

/**
 * Textarea -- a multi-line text field, adapted from the same reference kit as Button (see
 * button.tsx's header comment). Like Input (input.tsx) it is a styled native element with no
 * headless primitive behind it: standard Tailwind utilities reading `@didact/theme`'s tokens, the
 * same `data-slot="textarea"` attribute, and the shared focus-outline / `aria-invalid` treatment.
 * Its reference shadow is intentionally removed in favor of a fixed border.
 */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:focus-visible:outline-destructive md:text-sm dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
