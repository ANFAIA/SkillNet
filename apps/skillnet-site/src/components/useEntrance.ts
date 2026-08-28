import { useLayoutEffect, useRef, useState } from "react";
import { useInView, useReducedMotion, type Variants } from "framer-motion";

const EASE = [0.38, 0.49, 0, 1] as const;

export const revealGroup: Variants = {
  hidden: { transition: { staggerChildren: 0 } },
  show: { transition: { delayChildren: 0.04, staggerChildren: 0.09 } },
};

export const revealItem: Variants = {
  hidden: { opacity: 0, y: 18, transition: { duration: 0 } },
  show: { opacity: 1, y: 0, transition: { duration: 0.58, ease: EASE } },
};

/**
 * Entrance animation state that survives server rendering.
 *
 * framer-motion writes its `initial` styles into the HTML Astro renders on the
 * server, so an `initial="hidden"` element ships as `opacity: 0` and stays
 * invisible until React hydrates (forever, with JavaScript off). Instead the
 * markup is rendered in its final state and the hidden state is armed on the
 * client inside a layout effect -- that runs before the browser paints, so the
 * final state is never shown and then hidden again.
 *
 * Pair it with `initial={false}` and `animate={state}` on every motion element,
 * and give the `hidden` variant a zero duration so arming is instant.
 */
export function useEntrance<T extends Element>(amount = 0.35) {
  const ref = useRef<T | null>(null);
  const reduced = useReducedMotion() ?? false;
  const [armed, setArmed] = useState(false);
  const inView = useInView(ref, { once: true, amount });

  useLayoutEffect(() => {
    if (!reduced) setArmed(true);
  }, [reduced]);

  const state: "hidden" | "show" = !armed || reduced || inView ? "show" : "hidden";

  return { ref, reduced, state };
}
