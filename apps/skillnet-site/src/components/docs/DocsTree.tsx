import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";
import type { DocsFileTreeNode } from "../../data/docsNav";

interface Props {
  nodes: DocsFileTreeNode[];
  openIds: string[];
  currentSlug?: string;
  locale: "es" | "en";
}

/** Root indent, plus one step per level of depth. */
const INDENT_BASE = 8;
const INDENT_STEP = 12;

/** Trailing slashes vary between the built pages and the hrefs; ignore them. */
const normalize = (path: string) => path.replace(/\/+$/, "") || "/";

/** id -> ids of every branch above it, plus href -> id, for the whole tree. */
function indexTree(nodes: DocsFileTreeNode[]) {
  const ancestors = new Map<string, string[]>();
  const byHref = new Map<string, string>();
  const walk = (list: DocsFileTreeNode[], trail: string[]) => {
    for (const node of list) {
      ancestors.set(node.id, trail);
      if (node.href) byHref.set(normalize(node.href), node.id);
      walk(node.children, [...trail, node.id]);
    }
  };
  walk(nodes, []);
  return { ancestors, byHref };
}

const COPY = {
  es: { nav: "Navegación de documentación", expand: "Desplegar", collapse: "Plegar" },
  en: { nav: "Documentation navigation", expand: "Expand", collapse: "Collapse" },
} as const;

export default function DocsTree({ nodes, openIds, currentSlug, locale }: Props) {
  const reduced = useReducedMotion() ?? false;
  const copy = COPY[locale];

  // The whole tree renders open on the server and is collapsed on the client
  // inside a layout effect, before the first paint. framer-motion serializes the
  // styles it would animate from into the server HTML, so a tree that started
  // closed would ship its links at `opacity: 0` / `height: 0` — invisible without
  // JavaScript and to a crawler. This is the useEntrance pattern, applied to a
  // collapsed state instead of an entrance.
  const [armed, setArmed] = useState(false);
  const [open, setOpen] = useState<Set<string>>(() => new Set(openIds));
  const [currentId, setCurrentId] = useState<string | undefined>(
    currentSlug === undefined ? undefined : `doc:${currentSlug}`,
  );
  // Arming itself must not animate; only what the reader does afterwards.
  const settled = useRef(false);

  useLayoutEffect(() => {
    setArmed(true);
  }, []);

  useEffect(() => {
    if (armed) settled.current = true;
  }, [armed]);

  const animate = armed && !reduced && settled.current;

  // Docs pages navigate with Astro's view transitions and this panel carries
  // `transition:persist`, so the tree DOM — and this React state — survives the
  // swap. That is the point: no remount, no re-collapse, no entrance replayed,
  // and the folders the reader opened stay open. The cost is that nothing here
  // is told the page changed, so the selection would keep pointing at the page
  // left behind. The URL is the one thing that is always right, so read it.
  useEffect(() => {
    const { ancestors, byHref } = indexTree(nodes);
    const sync = () => {
      const id = byHref.get(normalize(window.location.pathname));
      setCurrentId(id);
      // A page reached from the article body may sit in a folder the reader has
      // closed; open the way down to it so the selection is never hidden.
      if (id) {
        const trail = ancestors.get(id) ?? [];
        setOpen((prev) => (trail.every((a) => prev.has(a)) ? prev : new Set([...prev, ...trail])));
      }
    };
    sync();
    document.addEventListener("astro:page-load", sync);
    return () => document.removeEventListener("astro:page-load", sync);
  }, [nodes]);

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <nav aria-label={copy.nav} className="docs-tree">
      <Branch
        nodes={nodes}
        depth={0}
        parentOpen
        open={open}
        armed={armed}
        animate={animate}
        toggle={toggle}
        currentId={currentId}
        copy={copy}
      />
    </nav>
  );
}

interface BranchProps {
  nodes: DocsFileTreeNode[];
  depth: number;
  parentOpen: boolean;
  open: Set<string>;
  armed: boolean;
  animate: boolean;
  toggle: (id: string) => void;
  currentId?: string;
  copy: (typeof COPY)[keyof typeof COPY];
}

function Branch({ nodes, depth, parentOpen, open, armed, animate, toggle, currentId, copy }: BranchProps) {
  return (
    <ul className="docs-tree__list">
      {nodes.map((node, index) => {
        // Before arming, every branch is open: that is what the server renders.
        const isOpen = !armed || open.has(node.id);
        const isFolder = node.children.length > 0;
        const isCurrent = node.id === currentId;
        const padding = INDENT_BASE + depth * INDENT_STEP;
        const Icon = isFolder ? (isOpen ? FolderOpen : Folder) : FileText;

        const chevron = (
          <motion.span
            className="docs-tree__chevron"
            initial={false}
            animate={{ rotate: isOpen ? 90 : 0 }}
            transition={{ duration: animate ? 0.2 : 0 }}
            aria-hidden="true"
          >
            <ChevronRight size={12} strokeWidth={2} />
          </motion.span>
        );

        const icon = <Icon className="docs-tree__icon" size={16} strokeWidth={1.75} aria-hidden="true" />;

        return (
          <motion.li
            key={node.id}
            className="docs-tree__item"
            initial={false}
            animate={{ opacity: parentOpen ? 1 : 0, y: parentOpen ? 0 : -12 }}
            transition={{
              duration: animate ? 0.25 : 0,
              ease: "easeInOut",
              // The cascade: each row follows the one above it on the way in, and
              // the order reverses on the way out.
              delay: animate ? 0.03 * (parentOpen ? index : nodes.length - 1 - index) : 0,
            }}
          >
            {node.href === undefined ? (
              // A section has no page of its own, so the whole row is the control.
              <button
                type="button"
                className="docs-tree__row docs-tree__row--folder"
                style={{ paddingLeft: `${padding}px` }}
                aria-expanded={isOpen}
                aria-controls={`${node.id}-children`}
                onClick={() => toggle(node.id)}
              >
                {chevron}
                {icon}
                <span className="docs-tree__label docs-tree__label--section">{node.label}</span>
              </button>
            ) : (
              <div className="docs-tree__row" style={{ paddingLeft: `${padding}px` }}>
                {isFolder ? (
                  <button
                    type="button"
                    className="docs-tree__toggle"
                    aria-expanded={isOpen}
                    aria-controls={`${node.id}-children`}
                    aria-label={`${isOpen ? copy.collapse : copy.expand}: ${node.label}`}
                    onClick={() => toggle(node.id)}
                  >
                    {chevron}
                  </button>
                ) : (
                  // A file keeps the chevron's width so the names stay aligned.
                  <span className="docs-tree__chevron docs-tree__chevron--empty" aria-hidden="true" />
                )}
                {icon}
                <a
                  href={node.href}
                  className="docs-tree__label docs-tree__link"
                  aria-current={isCurrent ? "page" : undefined}
                >
                  {/* The text sits in its own span so the anchor can stretch to
                      the full height of the row — on a phone the row is taller
                      than the line, and a tap on that padding must still follow
                      the link — while the ellipsis stays on the text itself. */}
                  <span className="docs-tree__text">{node.label}</span>
                </a>
              </div>
            )}

            {isFolder && (
              <motion.div
                id={`${node.id}-children`}
                className="docs-tree__children"
                initial={false}
                animate={{ height: isOpen ? "auto" : 0 }}
                transition={{ duration: animate ? 0.2 : 0, ease: "easeInOut" }}
                // A closed branch keeps its links in the HTML (they must stay
                // readable without JavaScript) but must leave the tab order.
                inert={!isOpen}
              >
                <Branch
                  nodes={node.children}
                  depth={depth + 1}
                  parentOpen={isOpen}
                  open={open}
                  armed={armed}
                  animate={animate}
                  toggle={toggle}
                  currentId={currentId}
                  copy={copy}
                />
              </motion.div>
            )}
          </motion.li>
        );
      })}
    </ul>
  );
}
