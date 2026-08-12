import * as React from "react";

import { cn } from "../lib/cn.js";

/**
 * Input -- a single-line text field, adapted from the same reference kit as Button (see
 * button.tsx's header comment for the porting rationale). It is a styled native `<input>` with no
 * headless-primitive behind it (a text field needs none): standard Tailwind utilities reading
 * `@didact/theme`'s tokens (`border-input`, `bg-transparent`, `text-foreground`, the shared
 * focus-outline and `aria-invalid` treatments), and the same `data-slot="input"` attribute. Its
 * reference shadow and box-shadow focus ring are replaced by a fixed border and CSS outline.
 *
 * Accessibility: pair every Input with a `Label` (label.tsx) via `htmlFor`/`id`, and drive its
 * error state with `aria-invalid` + real error text referenced by `aria-describedby` (never the
 * red outline alone) -- docs/interface-norms.md "Focus & states".
 */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base transition-colors outline-none selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30",
        "focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "aria-invalid:border-destructive aria-invalid:focus-visible:outline-destructive",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
