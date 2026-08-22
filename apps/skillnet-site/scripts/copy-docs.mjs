// One-off helper used to populate src/content/docs/*.md from docs/design/*.md
// and RUNNING.md. Not part of the build — run manually after editing source
// docs in ../../docs/design, then re-run `npm run build` to verify.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const destDir = join(here, "..", "src", "content", "docs");

const entries = [
  { slug: "quickstart", title: "Arranque rápido", order: 1, section: "start", src: join(repoRoot, "RUNNING.md") },
  { slug: "architecture", title: "Arquitectura", order: 2, section: "core", src: join(repoRoot, "docs/design/architecture.md") },
  { slug: "backend-api", title: "API backend", order: 3, section: "core", src: join(repoRoot, "docs/design/backend-api.md") },
  { slug: "data-model", title: "Modelo de datos", order: 4, section: "core", src: join(repoRoot, "docs/design/data-model.md") },
  { slug: "content-generation", title: "Generación de contenido", order: 5, section: "core", src: join(repoRoot, "docs/design/content-generation.md") },
  { slug: "chat-agents", title: "Chat y agentes", order: 6, section: "core", src: join(repoRoot, "docs/design/chat-agents.md") },
  { slug: "llm-integration", title: "Integración LLM", order: 7, section: "core", src: join(repoRoot, "docs/design/llm-integration.md") },
  { slug: "rag-retrieval", title: "RAG y recuperación", order: 8, section: "core", src: join(repoRoot, "docs/design/rag-retrieval.md") },
  { slug: "security", title: "Seguridad", order: 9, section: "core", src: join(repoRoot, "docs/design/security.md") },
  { slug: "background-processing", title: "Procesos en segundo plano", order: 10, section: "core", src: join(repoRoot, "docs/design/background-processing.md") },
  { slug: "dynamic-courses", title: "Cursos dinámicos (v2)", order: 11, section: "v2", src: join(repoRoot, "docs/design/v2-dynamic-courses.md") },
  { slug: "course-scope", title: "Alcance de v1", order: 12, section: "v2", src: join(repoRoot, "docs/design/v1-scope.md") },
  { slug: "personalization", title: "Personalización", order: 13, section: "extensibility", src: join(repoRoot, "docs/design/personalization.md") },
  { slug: "media-artifacts", title: "Artefactos multimedia", order: 14, section: "extensibility", src: join(repoRoot, "docs/design/media-artifacts.md") },
  { slug: "extensibility", title: "Extensibilidad (MCP/A2A)", order: 15, section: "extensibility", src: join(repoRoot, "docs/design/extensibility.md") },
  { slug: "design-system", title: "Sistema de diseño", order: 16, section: "extensibility", src: join(repoRoot, "docs/design/design-system.md") },
  { slug: "ai-course-design", title: "Diseño de cursos con IA", order: 17, section: "extensibility", src: join(repoRoot, "docs/design/ai-course-design.md") },
  { slug: "audience-modes", title: "Modos de audiencia", order: 18, section: "extensibility", src: join(repoRoot, "docs/design/audience-modes.md") },
  { slug: "admin-library-talent", title: "Biblioteca y talento (admin)", order: 19, section: "extensibility", src: join(repoRoot, "docs/design/admin-library-and-talent.md") },
];

function escapeYaml(s) {
  return s.replace(/"/g, '\\"');
}

for (const e of entries) {
  const body = readFileSync(e.src, "utf8");
  const frontmatter = `---\ntitle: "${escapeYaml(e.title)}"\norder: ${e.order}\nsection: "${e.section}"\n---\n\n`;
  writeFileSync(join(destDir, `${e.slug}.md`), frontmatter + body, "utf8");
}

console.log(`Copied ${entries.length} docs into ${destDir}`);
