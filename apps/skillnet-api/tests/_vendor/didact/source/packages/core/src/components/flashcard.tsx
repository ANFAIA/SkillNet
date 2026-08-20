import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Button, Card, CardContent, CardFooter, ToggleGroup, ToggleGroupItem } from "@didact/ui";

import { cn } from "../lib/cn.js";

/**
 * Flashcard -- RF-1's front/back card with a flip interaction and a "known" / "needs review"
 * mark. Rebuilt (2026-08-11) on top of `@didact/ui` -- the primitive kit `docs/interface-norms.md`
 * exists to make composition from possible by construction -- to fix two product-owner-flagged
 * problems with the previous, bespoke-buttons version:
 *
 * 1. **No action hierarchy.** The old component rendered "Known" and "Needs review" as two
 *    equal-weight buttons at all times. This version has exactly one `default`-variant `Button`
 *    per view (interface-norms.md's Action hierarchy rule): "Reveal answer" on the front face.
 *    The rating control is a `ToggleGroup` (a single segmented "pick your rating" control, not
 *    two competing primaries) that only appears once there is something to rate.
 * 2. **Bad flow (rating before the answer was revealed).** The flip is now a one-way disclosure
 *    from the component's own UI: clicking "Reveal answer" flips front -> back and the rating
 *    `ToggleGroup` is rendered in `CardFooter` -- literally absent from the tree -- until that
 *    happens. There is no UI path to rate before revealing, and no UI path back to the question
 *    (a controlled caller can still drive `flipped` back to `false` itself, e.g. to reset when
 *    advancing to the next card -- see the `flipped`/`onFlip` docs below).
 *
 * Composition (docs/interface-norms.md "Card composition"): the Flashcard IS a `Card`. `Card`
 * itself supplies the surface (fill, fixed border, radius) and its fixed `px-6`/`py-6`/`gap-6`
 * padding is left alone, per that doc, rather than special-cased per instance -- `variant`/`size`
 * below only ever add classes on top (transparent for `outline`, max-width + face
 * text scale for `size`), never touch Card's own spacing. `CardContent` holds the flipping front/
 * back faces; `CardFooter` holds the rating `ToggleGroup`, rendered only once `flipped` is true.
 *
 * Controlled / uncontrolled (docs/design-principles.md's customization mechanisms apply to
 * behavior props too): both `flipped` and `status` follow the standard React pattern -- pass the
 * prop to drive the value yourself (and update it from `onFlip`/`onMark`), or leave it out and let
 * the component track its own state, seeded from `defaultFlipped`/`defaultStatus`. `onFlip` now
 * only ever fires with `true` (the component's own UI is a one-way reveal, see above); a
 * controlled caller remains free to pass `flipped={false}` itself whenever it wants the front
 * face back (e.g. loading the next card), independently of what this component's UI does.
 *
 * Flip mechanism: unchanged from the previous version and kept deliberately -- the product owner
 * explicitly liked the 3D flip. A real 3D transform (`rotateY`), not a crossfade -- the front and
 * back are two faces of one rotating element (`backface-visibility: hidden` on each), stacked in
 * the same grid cell (`col-start-1 row-start-1` on both) so the card's height follows whichever
 * face is currently larger. The rotation uses a standard Tailwind duration utility (`duration-200`)
 * with `motion-reduce:transition-none` so `prefers-reduced-motion` (RF-13, WCAG 2.3.3) turns the
 * flip into an instant state change, with no separate reduced-motion branch needed in this file.
 * Motion carries no information of its own: the revealed face's presence in the accessibility tree
 * and the rating control's appearance are what convey the state change, not the animation.
 *
 * Accessibility:
 * - The reveal control is a real `@didact/ui` `Button` (`variant="default"`, native keyboard
 *   support) with a static accessible name ("Reveal answer") and `aria-expanded` reflecting
 *   whether the back is showing -- WCAG 2.1.1 (Keyboard) + 4.1.2 (Name, Role, Value). This is a
 *   disclosure ("reveal what's underneath"), not a two-state toggle, hence `aria-expanded` rather
 *   than `aria-pressed` here; the rating `ToggleGroupItem`s below (real two-state toggles) get
 *   `aria-pressed`/`data-state` for free from `@radix-ui/react-toggle-group`.
 * - Both faces stay mounted (a flashcard's back is meant to be revealed, so keeping it in the DOM
 *   is fine, unlike e.g. Hint/Reveal's answer-leak concern), but the face that is not currently
 *   showing is taken out of the accessibility tree with `aria-hidden` + `inert` (the latter also
 *   stops it from being keyboard-focusable, which is what makes the front face's "Reveal answer"
 *   button unreachable once the card has flipped, with no extra disabled-state bookkeeping) --
 *   so a screen-reader or keyboard user only ever encounters the one face that is visually
 *   showing.
 * - The rating control is a `ToggleGroup` (`type="single"`), which reads to assistive tech as one
 *   group with a role/name ("Rate your recall"), not two independent buttons that happen to sit
 *   next to each other -- RF-12 / WCAG 1.4.1 Use of Color still applies within it: each
 *   `ToggleGroupItem` carries its own text ("Known" / "Needs review") plus a decorative
 *   (`aria-hidden`) icon, and the selected item is only ever reinforced, never carried solely, by
 *   `Toggle`'s background-color change for `data-state=on`.
 * - Every interactive element's focus style comes from `@didact/ui`'s `Button`/`Toggle`, which
 *   already read the theme's ring token with the same 2px offset outline plus ring-colored
 *   border used across Didact (docs/visual-language.md, "Focus") -- WCAG 2.4.7. Nothing in this
 *   file reimplements or overrides that.
 *
 * Customization (docs/design-principles.md §1-3): `variant` (`default` | `outline`) and `size`
 * (`sm` | `md` | `lg`) are `cva`-driven named looks layered on top of `Card`'s own styling;
 * `className` is merged LAST via `cn()` so a single instance can be restyled inline. `size` also
 * scales the reveal `Button` and the rating `ToggleGroup` (`sm`/`default`/`lg`) so the two line up
 * with each other, per interface-norms.md's "Spacing & sizing" (pick a size scale for the whole
 * view). `asChild` is not offered here -- this is a stateful interactive widget with its own
 * internal layout, not a styling wrapper around a single consumer-supplied element.
 */

export type FlashcardStatus = "known" | "review";

const flashcardSizeToControlSize = {
  sm: "sm",
  md: "default",
  lg: "lg",
} as const;

const flashcardVariants = cva("w-full", {
  variants: {
    variant: {
      default: "",
      outline: "bg-transparent",
    },
    size: {
      sm: "max-w-xs",
      md: "max-w-sm",
      lg: "max-w-md",
    },
  },
  defaultVariants: {
    variant: "default",
    size: "md",
  },
});

const flashcardFaceVariants = cva(
  "col-start-1 row-start-1 flex flex-col items-center justify-center gap-3 text-center [backface-visibility:hidden]",
  {
    variants: {
      size: {
        sm: "min-h-24 text-sm",
        md: "min-h-32 text-base",
        lg: "min-h-40 text-lg",
      },
    },
    defaultVariants: {
      size: "md",
    },
  },
);

function CheckIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  );
}

function RepeatIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M2.5 8a5.5 5.5 0 0 1 9.5-3.8l1 1" />
      <path d="M13 2.2V5.4h-3.2" />
      <path d="M13.5 8a5.5 5.5 0 0 1-9.5 3.8l-1-1" />
      <path d="M3 13.8V10.6h3.2" />
    </svg>
  );
}

export interface FlashcardProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "onClick">,
    VariantProps<typeof flashcardVariants> {
  /** Content shown on the front (question) face. Always in the DOM; see the class doc above. */
  front: React.ReactNode;
  /** Content shown on the back (answer) face. Always in the DOM; see the class doc above. */
  back: React.ReactNode;
  /** Controlled flip state -- when provided, the caller owns whether the back is showing. */
  flipped?: boolean;
  /** Initial flip state for uncontrolled usage. Ignored once `flipped` is provided. */
  defaultFlipped?: boolean;
  /**
   * Fires when the reveal control is activated, in both controlled and uncontrolled usage.
   * Always fires with `true` -- revealing is a one-way disclosure from this component's own UI
   * (see the reveal -> rate flow note above); a controlled caller can still set `flipped={false}`
   * itself whenever it wants the front face shown again.
   */
  onFlip?: (flipped: boolean) => void;
  /** Controlled mark state -- when provided, the caller owns which mark (if any) is shown. */
  status?: FlashcardStatus;
  /** Initial mark state for uncontrolled usage. Ignored once `status` is provided. */
  defaultStatus?: FlashcardStatus;
  /** Fires whenever a rating is picked, in both controlled and uncontrolled usage. */
  onMark?: (status: FlashcardStatus) => void;
}

export const Flashcard = React.forwardRef<HTMLDivElement, FlashcardProps>(function Flashcard(
  {
    front,
    back,
    flipped: flippedProp,
    defaultFlipped = false,
    onFlip,
    status: statusProp,
    defaultStatus,
    onMark,
    variant,
    size,
    className,
    ...props
  },
  ref,
) {
  const isFlippedControlled = flippedProp !== undefined;
  const [uncontrolledFlipped, setUncontrolledFlipped] = React.useState(defaultFlipped);
  const flipped = isFlippedControlled ? flippedProp : uncontrolledFlipped;

  const isStatusControlled = statusProp !== undefined;
  const [uncontrolledStatus, setUncontrolledStatus] = React.useState<FlashcardStatus | undefined>(
    defaultStatus,
  );
  const status = isStatusControlled ? statusProp : uncontrolledStatus;

  const reveal = () => {
    if (!isFlippedControlled) setUncontrolledFlipped(true);
    onFlip?.(true);
  };

  const mark = (next: FlashcardStatus) => {
    if (!isStatusControlled) setUncontrolledStatus(next);
    onMark?.(next);
  };

  const handleRatingChange = (value: string) => {
    // Radix's single-select ToggleGroup calls onValueChange("") when the pressed item is clicked
    // again (deselecting it) -- not a valid FlashcardStatus, so it's ignored rather than passed to
    // onMark/setUncontrolledStatus.
    if (value === "known" || value === "review") mark(value);
  };

  const resolvedSize = size ?? "md";
  const controlSize = flashcardSizeToControlSize[resolvedSize];

  return (
    <Card
      ref={ref}
      className={cn(flashcardVariants({ variant, size }), className)}
      data-flipped={flipped}
      data-status={status ?? "unmarked"}
      {...props}
    >
      <CardContent>
        <div className="[perspective:1000px]">
          <div
            className={cn(
              "grid [transform-style:preserve-3d] transition-transform duration-200 ease-in-out motion-reduce:transition-none",
              flipped ? "[transform:rotateY(180deg)]" : "[transform:rotateY(0deg)]",
            )}
          >
            <div
              className={flashcardFaceVariants({ size })}
              aria-hidden={flipped}
              inert={flipped || undefined}
            >
              <div>{front}</div>
              <Button type="button" size={controlSize} onClick={reveal} aria-expanded={flipped}>
                Reveal answer
              </Button>
            </div>
            <div
              className={cn(flashcardFaceVariants({ size }), "[transform:rotateY(180deg)]")}
              aria-hidden={!flipped}
              inert={!flipped || undefined}
            >
              {back}
            </div>
          </div>
        </div>
      </CardContent>

      {flipped ? (
        <CardFooter className="justify-center">
          <ToggleGroup
            type="single"
            variant="outline"
            size={controlSize}
            value={status ?? ""}
            onValueChange={handleRatingChange}
            aria-label="Rate your recall"
          >
            <ToggleGroupItem value="known" aria-label="Known">
              <CheckIcon className="size-4" />
              Known
            </ToggleGroupItem>
            <ToggleGroupItem value="review" aria-label="Needs review">
              <RepeatIcon className="size-4" />
              Needs review
            </ToggleGroupItem>
          </ToggleGroup>
        </CardFooter>
      ) : null}
    </Card>
  );
});
