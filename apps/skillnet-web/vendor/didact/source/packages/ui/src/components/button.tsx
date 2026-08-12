import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "../lib/cn.js";

/**
 * Button -- the foundational action primitive of `@didact/ui` (layers 1-2 of the 3-layer
 * architecture, design.md §2). Based on the reference design system named in
 * `requirements.md` §0.2 -- same variant/size set and component anatomy (standard Tailwind
 * utilities reading `@didact/theme`'s tokens, e.g. `bg-primary`, `text-primary-foreground`), same
 * `data-slot`/`data-variant`/`data-size` attributes, same `asChild`/Slot escape hatch. The only
 * deliberate visual difference is Didact's global zero-shadow rule: fixed borders and CSS focus
 * outlines replace surface shadows and box-shadow focus rings.
 *
 * Variants (docs/interface-norms.md, Action hierarchy): `default` is the one primary action per
 * view; `secondary`/`outline` are secondary actions; `ghost` is tertiary/low-emphasis; `link` is
 * navigation-like; `destructive` is a destructive action. Never render two `default` buttons
 * side by side -- see that doc for the full rule.
 *
 * Sizes: `default`, `xs`, `sm`, `lg`, `icon`, `icon-xs`, `icon-sm`, `icon-lg` -- the icon sizes are
 * square (`size-*`) with no text padding, for icon-only buttons that still need an accessible name
 * via `aria-label`.
 *
 * `asChild` (docs/design-principles.md §4): when true, Button renders its classes and behavior
 * onto the single child element (via Radix's `Slot`) instead of wrapping it in a `<button>` -- the
 * mechanism that lets Didact's button styling travel onto a router `<Link>` or any other custom
 * element that already owns its own semantics.
 */

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:focus-visible:outline-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:outline-destructive dark:bg-destructive/60",
        outline:
          "border border-border bg-background hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  /** Render onto the single child element instead of a `<button>` (docs/design-principles.md §4). */
  asChild?: boolean;
}

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
