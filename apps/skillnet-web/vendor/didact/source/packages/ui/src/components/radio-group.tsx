import * as React from "react";
import { RadioGroup as RadioGroupPrimitive } from "radix-ui";

import { cn } from "../lib/cn.js";

/**
 * RadioGroup / RadioGroupItem -- a single-select group of radio controls, ported from the same
 * reference kit as Button (see button.tsx's header comment). Backed by `radix-ui`'s `RadioGroup`
 * (the unified `radix-ui` package, same import style as Toggle/ToggleGroup), which owns the
 * roving-tabindex keyboard behavior and `aria-checked`/`data-state` for each item. Standard
 * Tailwind utilities reading `@didact/theme`'s tokens, the same `data-slot` attributes, and the
 * same component anatomy, with the reference shadow and focus ring replaced by a fixed border and
 * CSS focus outline.
 *
 * Two deviations from the reference source, both matching conventions already established in this
 * kit rather than the reference's own environment:
 * - the `cn` import path (`../lib/cn.js`), as in every other primitive here;
 * - the selected-state indicator is an inline SVG circle instead of an icon-library import, exactly
 *   as `flashcard.tsx` inlines its own icons -- Didact's kit deliberately ships no icon-library
 *   dependency (docs/interface-norms.md: add a dependency only when a component genuinely needs
 *   one, and a filled dot does not).
 */
function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn("grid gap-3", className)}
      {...props}
    />
  );
}

function RadioGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        "aspect-square size-4 shrink-0 rounded-full border border-input text-primary transition-colors outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:focus-visible:outline-destructive dark:bg-input/30",
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="relative flex items-center justify-center"
      >
        <svg
          viewBox="0 0 8 8"
          fill="currentColor"
          aria-hidden="true"
          focusable="false"
          className="absolute top-1/2 left-1/2 size-2 -translate-x-1/2 -translate-y-1/2 fill-primary"
        >
          <circle cx="4" cy="4" r="4" />
        </svg>
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );
}

export { RadioGroup, RadioGroupItem };
