// Build step: OpenUI Lang prompt + catalogue artefacts for the Python backend.
//
// The backend is Python and OpenUI's library is JavaScript, so nothing here may run
// at request time. This script runs at build time and writes two VERSIONED artefacts
// that Python reads as data:
//
//   apps/skillnet-api/src/render/openui_prompt.txt    <- library.prompt(...)  verbatim
//   apps/skillnet-api/src/render/openui_catalog.json  <- library.toSpec() + digests
//
// The component catalogue is therefore defined ONCE, in the frontend kit, and both
// the prompt the model sees and the signatures the Python validator enforces come
// from that single place. `tests/test_render_prompt_artifact.py` fails if the
// artefacts stop matching `src/render/kit.py` — that is the drift alarm, and it is
// also what will fire the day @openuidev changes its prompt API.
//
// Usage (from apps/skillnet-web):
//   node scripts/generate-openui-prompt.mjs           # regenerate from the kit
//   node scripts/generate-openui-prompt.mjs --check   # CI: fail if stale, write nothing
//   OPENUI_MODULES=/path/to/node_modules node scripts/generate-openui-prompt.mjs
//
// It writes `catalog_source` into the JSON, so which file the catalogue was read from is
// on the record and not folklore.

import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const WEB_ROOT = path.resolve(HERE, '..')
const API_RENDER_DIR = path.resolve(WEB_ROOT, '../skillnet-api/src/render')
const PROMPT_FILE = path.join(API_RENDER_DIR, 'openui_prompt.txt')
const CATALOG_FILE = path.join(API_RENDER_DIR, 'openui_catalog.json')

const args = new Set(process.argv.slice(2))
const CHECK_ONLY = args.has('--check')

// How the catalogue is found, in order of preference:
//
// 1. A module exporting a built library. Cheapest and most direct, but node cannot load
//    `library.tsx` (it strips TypeScript types and does NOT transform JSX), so this only
//    works if the kit also exposes a `.ts`/`.mjs` entry. Accepted export names:
//    `promptLibrary` / `library` (the 9 the model may emit) and optionally
//    `renderLibrary` / `libraryFull` / `skillnetLibrary` (those plus Markdown).
// 2. `kit/schemas.ts` — pure zod, no JSX, so node loads it directly. This is the path in
//    use today: the prop names, their POSITIONAL ORDER and every enum value come from the
//    frontend kit, and only the one-line descriptions live here (they are prompt copy).
// If neither is loadable the script fails: a build step that guesses the catalogue is
// worse than one that stops.
const LIBRARY_CANDIDATES = [
  'src/components/courses/kit/prompt-catalog.mjs',
  'src/components/courses/kit/prompt-catalog.ts',
  'src/components/courses/kit/catalog.mjs',
  'src/components/courses/kit/catalog.ts',
  'src/components/courses/kit/library.ts',
  'src/components/courses/kit/index.ts',
]

const SCHEMAS_CANDIDATES = [
  'src/components/courses/kit/schemas.ts',
  'src/components/courses/kit/schemas.mjs',
]

// name -> [zod export in kit/schemas.ts, description]. The order is the order of the §5.3
// table and therefore of the prompt catalogue. `Markdown` is last and is excluded from the
// prompt: the server authors it for fallback_seed, the model may not emit it.
const CATALOGUE = [
  ['Stack', 'stackProps', 'Contenedor vertical'],
  ['TextContent', 'textContentProps', 'Prosa'],
  ['Card', 'cardProps', 'Agrupar'],
  ['Callout', 'calloutProps', 'Regla critica, excepcion'],
  ['StepSequence', 'stepSequenceProps', 'Procedimiento (2-7 pasos)'],
  ['Table', 'tableProps', 'Comparar conceptos'],
  ['CodeBlock', 'codeBlockProps', 'Ejemplo de codigo'],
  ['Chart', 'chartProps', 'Dato cuantitativo'],
  ['QuizItem', 'quizItemProps', 'Ejercicio'],
  ['SliderExploration', 'sliderExplorationProps', 'Explorar un parametro con slider interactivo'],
  ['ManipulableGraph', 'manipulableGraphProps', 'Plano cartesiano interactivo con puntos y funciones'],
  ['BeforeAfter', 'beforeAfterProps', 'Comparar dos estados con divisor deslizante'],
  ['Markdown', 'markdownProps', 'Solo para fallback_seed; el modelo no puede emitirlo'],
  ['DragOrder', 'dragOrderProps', 'Reordenar arrastrando'],
  ['HotspotImage', 'hotspotImageProps', 'Imagen con zonas interactivas'],
  ['StepByStepReveal', 'stepByStepRevealProps', 'Revelacion progresiva de pasos'],
  ['AudioExplanation', 'audioExplanationProps', 'Texto leido en voz alta con resaltado de palabras'],
  ['PronunciationExercise', 'pronunciationExerciseProps', 'Escuchar y practicar pronunciacion con comparacion de ondas'],
  ['DiagramBuilder', 'diagramBuilderProps', 'Diagrama SVG que se construye paso a paso'],
  ['Tabs', 'tabsProps', 'Pestanas para mostrar contenido alternativo en el mismo espacio'],
  ['TabItem', 'tabItemProps', 'Panel de una pestana dentro de Tabs'],
  ['Accordion', 'accordionProps', 'Secciones plegables de revelacion progresiva'],
  ['AccordionItem', 'accordionItemProps', 'Seccion plegable dentro de Accordion'],
]

// ---------------------------------------------------------------------------------
// The Spanish prompt SkillNet owns. `library.prompt()` contributes the syntax block,
// the signatures and the streaming/verification advice; everything below is ours,
// because their prompt has no room for the seven contract rules of §5.2, no room for
// the three escape rules of §5.4, and teaches syntax our gate rejects (rule 4 here
// overrides their "Syntax Rules 3" on purpose).
// ---------------------------------------------------------------------------------

const MAX_COMPONENTS = 12
const MAX_ROOT_CHILDREN = 5

const PREAMBLE = [
  'Eres el generador de pantallas de SkillNet, formacion de cumplimiento normativo',
  'para empleados. Responde UNICAMENTE con un programa en el dialecto descrito abajo:',
  'sin prosa antes ni despues, sin comentarios y sin JSON. Todos los textos que escribas',
  'van en el idioma del aprendiz (por defecto, espanol).',
].join('\n')

const ADDITIONAL_RULES = [
  // "Cada salto de linea real cierra un bloque" used to be stated here as a rule. It was
  // false: lang-core separates statements at bracket depth 0, so a newline inside an open
  // array continues the same declaration, and since 2026-07-27 the Python parser agrees
  // (src/render/lines.py). Teaching a rule the validator does not enforce is the same
  // defect as teaching a grammar narrower than the dialect — it costs a repair attempt on
  // a program that was already valid. It stays as a *preference*, which is what it is.
  'SkillNet 1 — Una declaracion por linea, preferiblemente. Ningun salto de linea ' +
    'literal dentro de una comilla: escribe \\n. Un salto de linea dentro de un array ' +
    'abierto continua la misma declaracion, asi que no la rompe, pero escribir cada ' +
    'declaracion entera en su linea hace que el aprendiz vea la pantalla montarse ' +
    'mientras se genera. Un bloque anidado en linea dentro del array de su padre es ' +
    'valido, y por lo mismo se prefiere declararlo aparte y referenciarlo por id.',
  'SkillNet 2 — Comilla doble dentro de un texto: escribela \\". Nunca sin escapar.',
  'SkillNet 3 — Table.rows es un array de arrays de texto, obligatoriamente: ' +
    'Table(["A", "B"], [["1", "2"], ["3", "4"]]).',
  // Inline nesting is deliberately NOT in this list: it is part of OpenUI Lang, the
  // signature block above recommends it as an option, and the backend parser accepts it
  // since 2026-07-27 (flattening it with synthetic ids). Teaching a construction and
  // then rejecting it was measured to cost the whole repair loop against a 7B model.
  'SkillNet 4 — Esto ANULA la regla de sintaxis 3 de arriba: en SkillNet NO existen los ' +
    'booleanos, ni null, ni los objetos {...}, ni los ' +
    'comentarios //, ni la aritmetica, ni las variables $estado, ni los builtins @Nombre, ' +
    'ni Query(...), ni Mutation(...), ni Action(...). Un programa que use cualquiera de esas ' +
    'formas se rechaza entero. Los unicos argumentos validos son texto entre comillas, ' +
    'numeros, arrays, referencias por id sin comillas y llamadas a bloques del catalogo.',
  `SkillNet 5 — Como maximo ${MAX_COMPONENTS} bloques en total.`,
  `SkillNet 6 — Como maximo ${MAX_ROOT_CHILDREN} elementos en el nivel raiz.`,
  'SkillNet 7 — El bloque raiz es un Stack o un Card, y ningun otro bloque lo referencia.',
  'SkillNet 8 — En los formatos explanation y mixed, el PRIMER hijo de la raiz es un ' +
    'TextContent con variant "lead" o un Callout: es el hueco de la linea que dice para que ' +
    'le sirve al aprendiz.',
  'SkillNet 9 — QuizItem NO lleva la respuesta correcta ni la explicacion: eso viaja por ' +
    'separado y nunca llega al navegador.',
  'SkillNet 10 — El texto es texto plano o marcado inline (**negrita**, *cursiva*, ' +
    '`literal`, enlaces). Nunca HTML.',
  'SkillNet 11 — Sin bloques repetidos: no digas lo mismo dos veces en dos formatos.',
  // Neutralises the library's own syntax rule 6, which is hard-wired in lang-core's
  // bundle (offset 9470) and has no `SystemPromptOptions` flag to switch it off. It
  // reads «Write `Stack([children], "row", "l")` NOT `Stack([children], direction:
  // "row", gap: "l")`» — an imperative example of a THREE-argument Stack with a `gap`
  // of "l", neither of which exists here. `Stack` is the root of every program, so it
  // is the first pattern a small model copies; measured, a program that copies it is
  // rejected outright (arity 3 over 2 props, "row" outside the enum), which burns the
  // single repair retry and lands on `fallback_seed`.
  'SkillNet 12 — Esto ANULA los ejemplos del bloque "Syntax Rules" de arriba: esas ' +
    'llamadas no son de este catalogo y algunas contradicen las firmas reales. La unica ' +
    'fuente de verdad es el bloque "Component Signatures". En concreto Stack tiene ' +
    'exactamente 2 argumentos, Stack([hijos], gap), y gap solo puede ser "sm", "md" o ' +
    '"lg": no existe ninguna direccion (nada de row ni column) ni ningun gap de una ' +
    'letra. Un Stack con 3 argumentos rechaza el programa entero.',
  // Neutralises the library's «## Important Rules» block (hard-wired at offset 23931,
  // also unsuppressable). In a compliance-training generator, "generate
  // realistic/plausible data" is the opposite of the product: every figure has to come
  // from the customer's document (§5.1). The block also advertises "forms for input",
  // a category the catalogue does not have.
  'SkillNet 13 — Esto ANULA el bloque "Important Rules" de arriba: NO inventes datos. ' +
    'Esto es formacion de cumplimiento normativo, asi que no escribas ninguna cifra, ' +
    'porcentaje, plazo, importe, fecha, sancion, nombre de norma ni referencia a un ' +
    'articulo que no aparezca literalmente en la fuente que se te ha dado. Si la fuente ' +
    'no lo dice, omite el dato y redacta la frase sin el; nunca lo rellenes con un valor ' +
    'plausible ni con un ejemplo inventado. Tampoco hay bloques de formulario ni de ' +
    'entrada de datos: los unicos bloques que existen son los de "Component Signatures".',
]

const EXAMPLES = [
  [
    'root = Stack([intro, pasos, quiz], "md")',
    'intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")',
    'pasos = StepSequence("Proceso de devolucion", ["Verificar el producto", ' +
      '"Escanear el ticket", "Registrar en el sistema", "Emitir el reembolso"])',
    'quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el dia 32. Que haces?", ' +
      '["Aceptar la devolucion", "Ofrecer garantia del fabricante", "Rechazar sin mas", ' +
      '"Llamar al encargado"])',
  ].join('\n'),
]

// ---------------------------------------------------------------------------------
// Module resolution. OPENUI_MODULES overrides the lookup so the script can run against
// an out-of-tree install.
// ---------------------------------------------------------------------------------

function requireFrom(dir) {
  return createRequire(path.join(dir, 'package.json'))
}

// OPENUI_MODULES is a node_modules directory (or the package root that owns one).
function moduleRoots() {
  const roots = []
  const override = process.env.OPENUI_MODULES
  if (override) {
    const trimmed = override.replace(/[/\\]+$/, '')
    roots.push(path.basename(trimmed) === 'node_modules' ? path.dirname(trimmed) : trimmed)
  }
  roots.push(WEB_ROOT)
  return roots
}

// `@openuidev/lang-core` is a transitive dependency of `@openuidev/react-lang`, so under
// pnpm it is not resolvable from the app root unless it is also a direct dependency. The
// second strategy resolves it exactly as the renderer does, which is what we want anyway:
// the build step must compile the catalogue with the same parser the browser will use.
function requireCandidates() {
  const requires = []
  for (const root of moduleRoots()) {
    let req
    try {
      req = requireFrom(root)
    } catch {
      continue
    }
    requires.push({ label: root, req })
    try {
      requires.push({
        label: `${root} (via @openuidev/react-lang)`,
        req: createRequire(req.resolve('@openuidev/react-lang')),
      })
    } catch {
      // react-lang not installed here; the direct require may still work.
    }
  }
  return requires
}

async function loadLangCore() {
  const tried = []
  for (const { label, req } of requireCandidates()) {
    try {
      const entry = req.resolve('@openuidev/lang-core')
      const mod = await import(pathToFileURL(entry).href)
      const zod = await import(pathToFileURL(req.resolve('zod')).href)
      return { mod, z: zod.z, root: label, versions: readVersions(req) }
    } catch (error) {
      tried.push(`${label}: ${error.code ?? error.message}`)
    }
  }
  throw new Error(
    '@openuidev/lang-core is not installed.\n' +
      'Add the pinned versions to apps/skillnet-web/package.json (exact, no caret):\n' +
      '  "@openuidev/lang-core": "0.2.10", "@openuidev/react-lang": "0.2.9", "zod": "4.4.3"\n' +
      'or point OPENUI_MODULES at a node_modules that has them.\n' +
      `Tried: ${tried.join(' | ')}`,
  )
}

function readVersions(req) {
  const versions = {}
  for (const name of ['@openuidev/lang-core', '@openuidev/react-lang', 'zod']) {
    try {
      // The packages do not export ./package.json, so read it off the resolved entry.
      let dir = path.dirname(req.resolve(name))
      for (let depth = 0; depth < 5; depth += 1) {
        const candidate = path.join(dir, 'package.json')
        if (fs.existsSync(candidate)) {
          const pkg = JSON.parse(fs.readFileSync(candidate, 'utf8'))
          if (pkg.name === name) {
            versions[name] = pkg.version
            break
          }
        }
        dir = path.dirname(dir)
      }
    } catch {
      versions[name] = null
    }
  }
  return versions
}

async function importCandidate(candidates) {
  const skipped = []
  for (const candidate of candidates) {
    const absolute = path.join(WEB_ROOT, candidate)
    if (!fs.existsSync(absolute)) continue
    try {
      return { mod: await import(pathToFileURL(absolute).href), source: candidate, skipped }
    } catch (error) {
      // A .tsx entry, a CSS import or a broken in-flight edit: say so and try the next.
      skipped.push(`${candidate}: ${error.code ?? error.message}`)
    }
  }
  return { mod: null, source: null, skipped }
}

// ---------------------------------------------------------------------------------
// Strategy 2: build the components from the kit's own zod schemas. `defineComponent`
// demands a `component`, and lang-core never inspects it — the renderer lives in
// `library.tsx`, which node cannot import, and it is irrelevant here.
// ---------------------------------------------------------------------------------

function componentsFromSchemas(schemas, { defineComponent }) {
  const missing = CATALOGUE.filter(([, exportName]) => !schemas[exportName])
  if (missing.length) {
    throw new Error(
      'kit/schemas.ts does not export ' +
        missing.map(([name, exportName]) => `${exportName} (${name})`).join(', ') +
        '. Either the catalogue changed or the export names did; fix this table.',
    )
  }
  const built = CATALOGUE.map(([name, exportName, description]) =>
    defineComponent({
      name,
      description,
      props: schemas[exportName],
      component: () => null,
    }),
  )
  const names = schemas.KIT_COMPONENT_NAMES
  if (names && [...names].join(',') !== CATALOGUE.map(([name]) => name).join(',')) {
    throw new Error(
      `kit/schemas.ts declares ${[...names].join(', ')} but this build step expects ` +
        `${CATALOGUE.map(([name]) => name).join(', ')}`,
    )
  }
  return {
    emittable: built.filter((component) => component.name !== 'Markdown'),
    all: built,
  }
}

// ---------------------------------------------------------------------------------
// Signature -> normalised catalogue. The digest is computed over the normalised form,
// not over the raw type annotations, so a cosmetic zod choice (z.array(z.any()) vs
// z.array(z.string()) for `children`) does not fire a false drift alarm, while a real
// change (a prop renamed, reordered, retyped, an enum value added) does.
// ---------------------------------------------------------------------------------

function splitTopLevel(text) {
  const parts = []
  let depth = 0
  let quoted = false
  let current = ''
  for (const char of text) {
    if (quoted) {
      current += char
      if (char === '"') quoted = false
      continue
    }
    if (char === '"') { quoted = true; current += char; continue }
    if ('([{'.includes(char)) depth += 1
    if (')]}'.includes(char)) depth -= 1
    if (char === ',' && depth === 0) { parts.push(current); current = ''; continue }
    current += char
  }
  if (current.trim()) parts.push(current)
  return parts.map((part) => part.trim()).filter(Boolean)
}

function normaliseKind(propName, annotation) {
  const type = annotation.trim()
  if (/^"/.test(type)) {
    const choices = type.split('|').map((choice) => choice.trim().replace(/^"|"$/g, ''))
    return { kind: 'enum', choices }
  }
  if (type.endsWith('[]') && propName === 'children') return { kind: 'ref[]', choices: [] }
  const known = ['string', 'number', 'string[]', 'string[][]', 'number[]', 'any[]']
  if (known.includes(type)) return { kind: type, choices: [] }
  return { kind: `unknown(${type})`, choices: [] }
}

function parseSignature(name, signature) {
  const open = signature.indexOf('(')
  const inner = signature.slice(open + 1, signature.lastIndexOf(')'))
  if (signature.slice(0, open) !== name) {
    throw new Error(`signature "${signature}" does not start with ${name}`)
  }
  return splitTopLevel(inner).map((field) => {
    const colon = field.indexOf(':')
    const rawName = (colon === -1 ? field : field.slice(0, colon)).trim()
    const optional = rawName.endsWith('?')
    const propName = optional ? rawName.slice(0, -1) : rawName
    const annotation = colon === -1 ? 'any' : field.slice(colon + 1)
    const { kind, choices } = normaliseKind(propName, annotation)
    return { name: propName, kind, choices, optional }
  })
}

function canonicalCatalogText(catalogId, root, components) {
  const lines = [`catalog: ${catalogId}`, `root: ${root}`]
  for (const component of components) {
    const props = component.props.map((prop) => {
      const kind = prop.kind === 'enum' ? `enum(${prop.choices.join('|')})` : prop.kind
      return `${prop.name}:${kind}${prop.optional ? '?' : ''}`
    })
    lines.push(`${component.name}(${props.join(', ')})`)
  }
  return lines.join('\n') + '\n'
}

const sha256 = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex')

// ---------------------------------------------------------------------------------

async function main() {
  const { mod: core, versions } = await loadLangCore()

  let promptLibrary = null
  let renderNames = null
  let catalogSource = null
  const notes = []

  // 1. A module that already exports a library.
  const asLibrary = await importCandidate(LIBRARY_CANDIDATES)
  notes.push(...asLibrary.skipped)
  if (asLibrary.mod) {
    const { promptLibrary: exported, library, LLM_COMPONENTS } = asLibrary.mod
    const rendered = asLibrary.mod.renderLibrary ?? asLibrary.mod.libraryFull ?? asLibrary.mod.skillnetLibrary
    promptLibrary =
      exported ??
      library ??
      (LLM_COMPONENTS
        ? core.createLibrary({ id: 'skillnet-ui/1', root: 'Stack', components: LLM_COMPONENTS })
        : null)
    if (!promptLibrary && rendered) {
      // Only a full library is exported: drop the components the model may not emit.
      const emittable = Object.values(rendered.components).filter(
        (component) => component.name !== 'Markdown',
      )
      promptLibrary = core.createLibrary({ id: rendered.id, root: rendered.root, components: emittable })
    }
    if (promptLibrary) {
      if (rendered) renderNames = Object.keys(rendered.toSpec().components)
      catalogSource = asLibrary.source
    } else {
      notes.push(
        `${asLibrary.source}: exports no library (promptLibrary / library / LLM_COMPONENTS)`,
      )
    }
  }

  // 2. The kit's zod schemas, which node can load because they carry no JSX.
  if (!promptLibrary) {
    const asSchemas = await importCandidate(SCHEMAS_CANDIDATES)
    notes.push(...asSchemas.skipped)
    if (asSchemas.mod) {
      const { emittable, all } = componentsFromSchemas(asSchemas.mod, core)
      promptLibrary = core.createLibrary({
        id: 'skillnet-ui/1',
        root: 'Stack',
        components: emittable,
      })
      renderNames = all.map((component) => component.name)
      catalogSource = asSchemas.source
    }
  }

  if (!promptLibrary) {
    throw new Error(
      'No usable frontend catalogue. Tried:\n  ' +
        [...LIBRARY_CANDIDATES, ...SCHEMAS_CANDIDATES].join('\n  ') +
        (notes.length ? `\nWhy each failed:\n  ${notes.join('\n  ')}` : '') +
        '\nA build step that guesses the catalogue would be worse than one that stops.',
    )
  }
  if (notes.length) console.warn(`note: ${notes.join('\n      ')}`)

  // No `tools`, no toolCalls, no bindings, no markReactive: the reactive syntax must
  // never appear in the system prompt (SEGURIDAD-MUTACIONES.md, control 5). Passing
  // `tools` would teach $state, ternaries, @Set and @Run in one block, and the flags
  // cannot switch that off by halves.
  const promptText = promptLibrary.prompt({
    preamble: PREAMBLE,
    additionalRules: ADDITIONAL_RULES,
    examples: EXAMPLES,
  })

  // Checked against the LIBRARY's own contribution, not against `promptText`: our
  // SkillNet rule 4 names Query/Mutation/Action in order to forbid them, and a grep
  // over the whole text would flag that legitimate prose (the same false positive
  // SEGURIDAD-MUTACIONES.md measured on lessons that mention "Query()").
  const libraryOnly = promptLibrary.prompt()
  const reactive = /\$var|\bQuery\(|\bMutation\(|\bAction\(|@Run\b|@Set\b|@Reset\b|@Each\b|\$binding/
  if (reactive.test(libraryOnly)) {
    throw new Error(
      'the generated prompt mentions reactive syntax. Something registered a tool or ' +
        'called markReactive() in the kit; fix the kit, do not weaken this check.',
    )
  }

  const spec = promptLibrary.toSpec()
  const components = Object.entries(spec.components).map(([name, definition]) => ({
    name,
    description: definition.description ?? '',
    signature: definition.signature,
    props: parseSignature(name, definition.signature),
  }))

  const catalogId = promptLibrary.id ?? 'skillnet-ui/1'
  const canonical = canonicalCatalogText(catalogId, spec.root, components)
  const catalogDigest = sha256(canonical)
  const promptBytes = promptText.endsWith('\n') ? promptText : `${promptText}\n`

  const catalog = {
    generated_by: 'apps/skillnet-web/scripts/generate-openui-prompt.mjs',
    catalog_source: catalogSource,
    catalog_id: catalogId,
    root: spec.root,
    library_versions: versions,
    prompt_components: components,
    render_components: renderNames,
    canonical_catalog: canonical,
    catalog_digest: catalogDigest,
    catalog_version: `${catalogId}+${catalogDigest.slice(0, 12)}`,
    prompt_sha256: sha256(promptBytes),
    prompt_chars: promptBytes.length,
  }
  const catalogBytes = `${JSON.stringify(catalog, null, 2)}\n`

  if (CHECK_ONLY) {
    const stale = []
    if (readOrNull(PROMPT_FILE) !== promptBytes) stale.push(PROMPT_FILE)
    if (readOrNull(CATALOG_FILE) !== catalogBytes) stale.push(CATALOG_FILE)
    if (stale.length) {
      console.error(
        'STALE OpenUI artefacts:\n  ' +
          stale.join('\n  ') +
          '\nRun: node scripts/generate-openui-prompt.mjs',
      )
      process.exit(1)
    }
    console.log(`OpenUI artefacts up to date (catalog ${catalog.catalog_version}).`)
    return
  }

  fs.writeFileSync(PROMPT_FILE, promptBytes, 'utf8')
  fs.writeFileSync(CATALOG_FILE, catalogBytes, 'utf8')
  console.log(
    `wrote ${path.relative(WEB_ROOT, PROMPT_FILE)} (${promptBytes.length} chars) and ` +
      `${path.relative(WEB_ROOT, CATALOG_FILE)}\n` +
      `  source=${catalogSource} version=${catalog.catalog_version} ` +
      `components=${components.length}`,
  )
}

function readOrNull(file) {
  try {
    return fs.readFileSync(file, 'utf8')
  } catch {
    return null
  }
}

await main()
