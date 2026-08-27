// Reports which site docs have fallen behind the repo docs they came from.
//
// It used to WRITE src/content/docs/en/*.md from docs/design/*.md, on the premise
// that en/ was a synced literal copy. That premise is dead twice over: the site's
// markdown links were rewritten by hand to site paths (/en/docs/<slug>) that a
// relative-link source cannot express, and several sources are in Spanish while
// their en/ counterpart is a hand-written translation. Overwriting either one
// destroys work — measured: a single run reverted the link fix across 58 files and
// pulled 2,271 unreviewed lines into en/snml-spec.md.
//
// So it reports and changes nothing. Both locales are maintained by hand; this
// says WHICH ones need attention, by comparing modification times against the
// source doc. Run it after editing anything under docs/design/ or RUNNING.md.

import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const destDir = join(here, "..", "src", "content", "docs", "en");
const esDir = join(here, "..", "src", "content", "docs", "es");

const entries = [
  { slug: "quickstart", title: "Arranque rápido", titleEn: "Quickstart", order: 1, section: "start", src: join(repoRoot, "RUNNING.md") },
  { slug: "configuration", title: "Configuración", titleEn: "Configuration", order: 2, section: "start", src: join(repoRoot, "docs/design/configuration.md") },
  { slug: "architecture", title: "Arquitectura", titleEn: "Architecture", order: 2, section: "core", src: join(repoRoot, "docs/design/architecture.md") },
  { slug: "backend-api", title: "API backend", titleEn: "Backend API", order: 3, section: "core", src: join(repoRoot, "docs/design/backend-api.md") },
  { slug: "data-model", title: "Modelo de datos", titleEn: "Data model", order: 4, section: "core", src: join(repoRoot, "docs/design/data-model.md") },
  { slug: "content-generation", title: "Generación de contenido", titleEn: "Content generation", order: 5, section: "core", src: join(repoRoot, "docs/design/content-generation.md") },
  { slug: "chat-agents", title: "Chat y agentes", titleEn: "Chat and agents", order: 6, section: "core", src: join(repoRoot, "docs/design/chat-agents.md") },
  { slug: "llm-integration", title: "Integración LLM", titleEn: "LLM integration", order: 7, section: "core", src: join(repoRoot, "docs/design/llm-integration.md") },
  { slug: "rag-retrieval", title: "RAG y recuperación", titleEn: "RAG and retrieval", order: 8, section: "core", src: join(repoRoot, "docs/design/rag-retrieval.md") },
  { slug: "security", title: "Seguridad", titleEn: "Security", order: 9, section: "core", src: join(repoRoot, "docs/design/security.md") },
  { slug: "background-processing", title: "Procesos en segundo plano", titleEn: "Background processing", order: 10, section: "core", src: join(repoRoot, "docs/design/background-processing.md") },
  { slug: "dynamic-courses", title: "Cursos dinámicos (v2)", titleEn: "Dynamic courses (v2)", order: 11, section: "v2", src: join(repoRoot, "docs/design/v2-dynamic-courses.md") },
  { slug: "course-scope", title: "Alcance de v1", titleEn: "v1 scope", order: 12, section: "v2", src: join(repoRoot, "docs/design/v1-scope.md") },
  { slug: "personalization", title: "Personalización", titleEn: "Personalization", order: 13, section: "extensibility", src: join(repoRoot, "docs/design/personalization.md") },
  { slug: "media-artifacts", title: "Artefactos multimedia", titleEn: "Media artifacts", order: 14, section: "extensibility", src: join(repoRoot, "docs/design/media-artifacts.md") },
  { slug: "extensibility", title: "Extensibilidad (MCP/A2A)", titleEn: "Extensibility (MCP/A2A)", order: 15, section: "extensibility", src: join(repoRoot, "docs/design/extensibility.md") },
  { slug: "design-system", title: "Sistema de diseño", titleEn: "Design system", order: 16, section: "extensibility", src: join(repoRoot, "docs/design/design-system.md") },
  { slug: "ai-course-design", title: "Diseño de cursos con IA", titleEn: "AI course design", order: 17, section: "extensibility", src: join(repoRoot, "docs/design/ai-course-design.md") },
  { slug: "audience-modes", title: "Modos de audiencia", titleEn: "Audience modes", order: 18, section: "extensibility", src: join(repoRoot, "docs/design/audience-modes.md") },
  { slug: "admin-library-talent", title: "Biblioteca y talento (admin)", titleEn: "Library and talent (admin)", order: 19, section: "extensibility", src: join(repoRoot, "docs/design/admin-library-and-talent.md") },

  // Rest of docs/design/*.md not yet covered by the original 19-doc subset.
  { slug: "vision", title: "Visión", titleEn: "Vision", order: 20, section: "start", src: join(repoRoot, "docs/design/vision.md") },
  { slug: "product", title: "Producto", titleEn: "Product", order: 21, section: "start", src: join(repoRoot, "docs/design/product.md") },
  { slug: "arquitectura-componentes-funcional", title: "Arquitectura de componentes funcional", titleEn: "Functional component architecture", order: 22, section: "core", src: join(repoRoot, "docs/design/arquitectura-componentes-funcional.md") },
  { slug: "frontend-backend-integration", title: "Integración frontend-backend", titleEn: "Frontend-backend integration", order: 23, section: "core", src: join(repoRoot, "docs/design/frontend-backend-integration.md") },
  { slug: "docker-deployment", title: "Despliegue con Docker", titleEn: "Docker deployment", order: 24, section: "core", src: join(repoRoot, "docs/design/docker-deployment.md") },
  { slug: "conversational-modalities", title: "Modalidades conversacionales", titleEn: "Conversational modalities", order: 25, section: "core", src: join(repoRoot, "docs/design/conversational-modalities.md") },
  { slug: "degraded-mode-ux", title: "UX en modo degradado", titleEn: "Degraded-mode UX", order: 26, section: "core", src: join(repoRoot, "docs/design/degraded-mode-ux.md") },
  { slug: "learning-experience-architecture", title: "Arquitectura de la experiencia de aprendizaje", titleEn: "Learning experience architecture", order: 27, section: "core", src: join(repoRoot, "docs/design/learning-experience-architecture.md") },
  { slug: "multi-agent-pipeline", title: "Pipeline multiagente", titleEn: "Multi-agent pipeline", order: 28, section: "core", src: join(repoRoot, "docs/design/multi-agent-pipeline.md") },
  { slug: "node-knowledge-packs", title: "Paquetes de conocimiento por nodo", titleEn: "Node knowledge packs", order: 29, section: "core", src: join(repoRoot, "docs/design/node-knowledge-packs.md") },
  { slug: "generacion-rica-preguntas-abiertas", title: "Generación rica de preguntas abiertas", titleEn: "Rich open-question generation", order: 30, section: "core", src: join(repoRoot, "docs/design/generacion-rica-preguntas-abiertas.md") },
  { slug: "rubrica-calidad-leccion", title: "Rúbrica de calidad de lección", titleEn: "Lesson quality rubric", order: 31, section: "core", src: join(repoRoot, "docs/design/rubrica-calidad-leccion.md") },
  { slug: "snml-spec", title: "Especificación SNML", titleEn: "SNML spec", order: 32, section: "core", src: join(repoRoot, "docs/design/snml-spec.md") },
  { slug: "tuning", title: "Ajuste de calidad", titleEn: "Tuning", order: 33, section: "core", src: join(repoRoot, "docs/design/tuning.md") },
  { slug: "delivery-modalities", title: "Modalidades de entrega", titleEn: "Delivery modalities", order: 34, section: "v2", src: join(repoRoot, "docs/design/delivery-modalities.md") },
  { slug: "future-prerequisites", title: "Prerrequisitos futuros", titleEn: "Future prerequisites", order: 35, section: "v2", src: join(repoRoot, "docs/design/future-prerequisites.md") },
  { slug: "future-product-directions", title: "Futuras direcciones de producto", titleEn: "Future product directions", order: 36, section: "v2", src: join(repoRoot, "docs/design/future-product-directions.md") },
  { slug: "adaptive-learning", title: "Aprendizaje adaptativo", titleEn: "Adaptive learning", order: 37, section: "extensibility", src: join(repoRoot, "docs/design/adaptive-learning.md") },
  { slug: "personalization-architecture", title: "Arquitectura de personalización", titleEn: "Personalization architecture", order: 38, section: "extensibility", src: join(repoRoot, "docs/design/personalization-architecture.md") },
  { slug: "generative-ui-personalization", title: "Personalización de UI generativa", titleEn: "Generative UI personalization", order: 39, section: "extensibility", src: join(repoRoot, "docs/design/generative-ui-personalization.md") },
  { slug: "brilliant-learning-patterns", title: "Patrones de aprendizaje tipo Brilliant", titleEn: "Brilliant-style learning patterns", order: 40, section: "extensibility", src: join(repoRoot, "docs/design/brilliant-learning-patterns.md") },
  { slug: "onboarding", title: "Incorporación (onboarding)", titleEn: "Onboarding", order: 41, section: "extensibility", src: join(repoRoot, "docs/design/onboarding.md") },
  { slug: "screens", title: "Pantallas", titleEn: "Screens", order: 42, section: "extensibility", src: join(repoRoot, "docs/design/screens.md") },
  { slug: "motion-system", title: "Sistema de movimiento", titleEn: "Motion system", order: 43, section: "extensibility", src: join(repoRoot, "docs/design/motion-system.md") },
  { slug: "openui-adoption", title: "Adopción de OpenUI", titleEn: "OpenUI adoption", order: 44, section: "extensibility", src: join(repoRoot, "docs/design/openui-adoption.md") },
  { slug: "mcp-external-api", title: "API externa MCP", titleEn: "MCP external API", order: 45, section: "extensibility", src: join(repoRoot, "docs/design/mcp-external-api.md") },
  { slug: "didact-components", title: "Componentes de Didact", titleEn: "Didact components", order: 46, section: "extensibility", src: join(repoRoot, "docs/design/didact-components.md") },
  { slug: "didact-integration", title: "Integración de Didact", titleEn: "Didact integration", order: 47, section: "extensibility", src: join(repoRoot, "docs/design/didact-integration.md") },
  { slug: "didact-integration-strategy", title: "Estrategia de integración de Didact", titleEn: "Didact integration strategy", order: 48, section: "extensibility", src: join(repoRoot, "docs/design/didact-integration-strategy.md") },
  { slug: "podcast-studio-plan", title: "Plan del estudio de podcast", titleEn: "Podcast studio plan", order: 49, section: "extensibility", src: join(repoRoot, "docs/design/podcast-studio-plan.md") },

  // docs/research/** — the investigative work, previously only published on
  // the standalone skillnet-docs (Vite+React) site.
  { slug: "research-overview", title: "Investigación: visión general", titleEn: "Research overview", order: 50, section: "research", src: join(repoRoot, "docs/research/README.md") },
  { slug: "semantic-boundaries", title: "Fronteras semánticas", titleEn: "Semantic boundaries", order: 51, section: "research", group: "semantic-boundaries", src: join(repoRoot, "docs/research/semantic-boundaries/README.md") },
  { slug: "semantic-boundaries-classification", title: "Clasificación basada en contenido", titleEn: "Content-based classification", order: 52, section: "research", group: "semantic-boundaries", src: join(repoRoot, "docs/research/semantic-boundaries/content-based-classification.md") },
  { slug: "semantic-boundaries-dsac-bench", title: "Banco DSAC", titleEn: "DSAC bench", order: 53, section: "research", group: "semantic-boundaries", src: join(repoRoot, "docs/research/semantic-boundaries/experiments/dsac-bench.md") },
  { slug: "semantic-boundaries-experiment-log", title: "Registro de experimentos", titleEn: "Experiment log", order: 54, section: "research", group: "semantic-boundaries", src: join(repoRoot, "docs/research/semantic-boundaries/experiments/experiment-log.md") },
  { slug: "generative-ui-research", title: "UI generativa (investigación)", titleEn: "Generative UI (research)", order: 55, section: "research", group: "generative-ui", src: join(repoRoot, "docs/research/generative-ui/README.md") },
  { slug: "generative-ui-benchmarks", title: "Bancos de prototipos", titleEn: "Prototype benchmarks", order: 56, section: "research", group: "generative-ui", src: join(repoRoot, "docs/research/generative-ui/experiments/prototype-benchmarks.md") },
  { slug: "multi-agent-coordination", title: "Coordinación multiagente", titleEn: "Multi-agent coordination", order: 57, section: "research", group: "multi-agent", src: join(repoRoot, "docs/research/multi-agent-coordination/README.md") },
  { slug: "multi-agent-communication", title: "Comunicación entre agentes", titleEn: "Agent communication", order: 58, section: "research", group: "multi-agent", src: join(repoRoot, "docs/research/multi-agent-coordination/agent-communication.md") },
  { slug: "post-markdown", title: "Post-Markdown", titleEn: "Post-Markdown", order: 59, section: "research", group: "post-markdown", src: join(repoRoot, "docs/research/post-markdown/README.md") },
  { slug: "post-markdown-md-reader", title: "Cómo funciona md-reader", titleEn: "How md-reader works", order: 60, section: "research", group: "post-markdown", src: join(repoRoot, "docs/research/post-markdown/how-md-reader-works.md") },
  { slug: "inference-acceleration", title: "Aceleración de inferencia", titleEn: "Inference acceleration", order: 61, section: "research", group: "inference", src: join(repoRoot, "docs/research/inference-acceleration/README.md") },
  { slug: "inference-production-roadmap", title: "Hoja de ruta de producción", titleEn: "Production roadmap", order: 62, section: "research", group: "inference", src: join(repoRoot, "docs/research/inference-acceleration/production-roadmap.md") },
];

function escapeYaml(s) {
  return s.replace(/"/g, '\\"');
}

const behind = [];

for (const e of entries) {
  const srcMtime = statSync(e.src).mtimeMs;
  for (const [locale, dir] of [["en", destDir], ["es", esDir]]) {
    const path = join(dir, `${e.slug}.md`);
    try {
      if (statSync(path).mtimeMs < srcMtime) behind.push(`${locale}/${e.slug}.md`);
    } catch {
      behind.push(`${locale}/${e.slug}.md (missing)`);
    }
  }
}

if (behind.length === 0) {
  console.log(`All ${entries.length * 2} site docs are at least as new as their source.`);
} else {
  const lines = behind.map((name) => `  - src/content/docs/${name}`);
  console.log("These site docs are older than the doc they came from:");
  for (const line of lines) console.log(line);
  console.log("");
  console.log("This script writes nothing. Edit the file in src/content/docs/ by hand.");
}
