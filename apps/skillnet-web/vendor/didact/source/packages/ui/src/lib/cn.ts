import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * `cn` -- Didact's class-composition helper (docs/design-principles.md §3), mirrored here from
 * packages/core/src/lib/cn.ts so `@didact/ui` has no dependency on `@didact/core`: `clsx` resolves
 * conditional/array/falsy class inputs, `tailwind-merge` then resolves conflicting Tailwind
 * utilities (e.g. a caller's `className="px-4"` overriding this component's own `px-2`) by keeping
 * the last one instead of leaving both in the DOM. Every Didact component that accepts `className`
 * must merge it LAST through this helper, not a manual array-join, so a single instance can be
 * restyled inline without fighting the base classes.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
