import * as React from "react";

import { cn } from "../lib/cn.js";

/**
 * Card family -- based on the same reference kit as Button (see button.tsx's header comment).
 * The reference shadow is intentionally removed in favor of a fixed border. Anatomy and slot names
 * are unchanged: `Card` (the surface) >
 * `CardHeader` (title + description + optional action, laid out with a container-query grid so the
 * action column only appears when a `CardAction` child is present) > `CardTitle` / `CardDescription`
 * / `CardAction` > `CardContent` (body) > `CardFooter` (actions). See docs/interface-norms.md,
 * "Card composition" for when to use each slot.
 *
 * Every slot carries a `data-slot` attribute (unchanged from the reference) so a consumer can
 * target a specific slot (e.g. `[data-slot=card-header]`) without relying on class names, and so
 * `CardHeader`'s own grid can react to whether a `CardAction` is present via
 * `has-data-[slot=card-action]`.
 */

function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col gap-6 rounded-xl border border-border bg-card py-6 text-card-foreground",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6",
        className,
      )}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("leading-none font-semibold", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("px-6", className)} {...props} />;
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center px-6 [.border-t]:pt-6", className)}
      {...props}
    />
  );
}

export { Card, CardHeader, CardFooter, CardTitle, CardAction, CardDescription, CardContent };
