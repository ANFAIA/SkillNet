# Perfil de organización: Gestión Tickets

**Estado:** propuesta de organización y fixture de evaluación; no es un seed de producción  
**Fecha de revisión:** 2026-08-12  
**Fixture asociado:** `../evidencia-testing/2026-08-12/gestion-tickets-profile/profile.json`

## Propósito

Este perfil traduce el corpus de Gestión Tickets a una estructura reutilizable
de SkillNet. No añade comportamiento especial para una empresa: sirve para probar si las
primitivas generales del producto - carpetas, cursos, competencias, rutas por rol, RAG y
experiencias generadas en el momento - resuelven una operación compleja con varias
plataformas, dispositivos y públicos.

La fuente revisada contiene 125 archivos: 64 PDF (1.044 páginas), 42 DOCX, 3 vídeos, 7
ejecutables y otros recursos. Hay duplicados, versiones antiguas, manuales de fabricante,
políticas, planos y credenciales mezclados con material formativo. Por tanto, **archivo no
equivale a curso**. La unidad educativa debe ser una tarea o decisión observable.

## Qué revela este caso para el producto

El corpus combina cinco necesidades distintas que SkillNet debe poder representar sin crear
una solución ad hoc:

1. **Aprender:** comprender un flujo y practicarlo con feedback.
2. **Ejecutar:** seguir una lista de comprobación durante una operación real.
3. **Consultar:** encontrar un dato o paso urgente sin completar antes un curso.
4. **Resolver incidencias:** diagnosticar síntomas y elegir una actuación segura.
5. **Acreditar:** dejar trazabilidad de que una persona puede ejecutar una tarea.

La consecuencia de producto es que una carpeta no debe contener solo cursos lineales. Puede
agrupar cursos, guías rápidas y recursos de referencia; el chat/RAG debe estar disponible
durante el aprendizaje y en el momento de trabajo. Completar un curso nunca debe bloquear la
consulta operativa.

## Taxonomía de carpetas propuesta

| Carpeta | Audiencia principal | Contenido | Criterio de salida |
| --- | --- | --- | --- |
| Fundamentos de la operación | Todas | vocabulario, ciclo del evento, plataformas y límites de responsabilidad | explica el ciclo y sabe dónde actuar |
| Gestión para organizadores | Organizador/promotor | alta y edición, entradas, ventas, invitaciones, cierre y consulta | publica y controla un evento de prueba |
| Taquilla y acceso | Taquilla/acceso | punto de venta, impresión, validación y respuesta en puerta | completa una apertura y resuelve casos comunes |
| Operación interna | Equipo de soporte | cuentas, publicación, configuración avanzada y recuperación | ejecuta procedimientos con comprobaciones |
| Cashless y GoFun | Operación cashless | productos, catálogos, estaciones, terminales, pulseras y recargas | configura un circuito de prueba consistente |
| Hardware e incidencias | Soporte técnico | Zebra, PAX, Sunmi, PDA, kioscos, conectividad y diagnóstico | identifica causa probable y escala con evidencia |
| Pagos y conciliación | Finanzas/soporte | pedidos, estados, devoluciones, cobros y lectura de paneles | interpreta estados sin exponer credenciales |
| Biblioteca de referencia | Según permisos | políticas, manuales de fabricante, planos y material no formativo | consulta; no genera competencia por lectura |

Las carpetas son una vista organizativa, no un límite de conocimiento. Una competencia puede
aparecer en cursos de varias carpetas y una persona puede recibir una ruta filtrada por rol.

## Catálogo inicial de cursos

### 1. El ciclo de un evento y el mapa de plataformas

- **Audiencia:** común.
- **Resultado:** distinguir creación, venta, cobro, acceso y cierre; elegir el sistema y el
  canal correctos para cada tarea.
- **Competencias:** `event-lifecycle`, `platform-routing`, `operational-boundaries`.
- **Experiencia:** mapa conceptual del ciclo, comparación de casos y escenario de derivación.
- **Didact:** `concept-map`, `categorize`, `branching-scenario`.

### 2. Crear, revisar y publicar un evento

- **Audiencia:** organizadores y equipo operativo, con profundidad distinta.
- **Resultado:** configurar identidad, sesiones, entradas, aforo, ubicación y publicación;
  realizar una revisión previa.
- **Competencias:** `event-creation`, `ticket-configuration`, `preflight-review`.
- **Experiencia:** ejemplo resuelto, checklist interactivo y anotación sobre una captura del
  panel. La pantalla concreta debe adaptarse a la plataforma seleccionada.
- **Didact:** `worked-example`, `timeline-steps`, `evidence-annotation`, `hotspot`.

### 3. Invitaciones, ventas privadas y permisos

- **Audiencia:** organizadores y equipo operativo.
- **Resultado:** escoger entre invitación individual, importación masiva y venta privada;
  evitar duplicidades y límites incorrectos.
- **Competencias:** `invitation-management`, `quota-safety`, `private-sales`.
- **Experiencia:** decisión por escenario, práctica de configuración y revisión de errores.
- **Didact:** `branching-scenario`, `worked-example`, `rubric`, `matching`.

### 4. Consultar ventas, pedidos y rendimiento

- **Audiencia:** organizadores, consultores y soporte.
- **Resultado:** localizar pedidos, filtrar, exportar y explicar métricas sin confundir venta,
  asistentes e ingreso.
- **Competencias:** `sales-monitoring`, `order-search`, `data-export`, `metric-literacy`.
- **Experiencia:** panel de datos con preguntas situacionales y comparación de indicadores.
- **Didact:** `data-explorer`, `numeric-question`, `self-explanation-prompt`.

### 5. Taquilla: preparación, venta e impresión

- **Audiencia:** personal de taquilla y soporte.
- **Resultado:** preparar equipo e impresora, iniciar la venta y comprobar una impresión de
  prueba siguiendo el orden seguro.
- **Competencias:** `box-office-opening`, `zebra-printing`, `point-of-sale-operation`.
- **Experiencia:** secuencia bloqueable, identificación visual de conexiones y diagnóstico.
- **Didact:** `timeline-steps`, `label-diagram`, `hotspot`, `branching-scenario`.

### 6. Control de acceso y validación de entradas

- **Audiencia:** acceso, organizadores y soporte.
- **Resultado:** configurar un dispositivo, interpretar válida/inválida/duplicada y actuar
  ante excepciones sin improvisar.
- **Competencias:** `access-device-setup`, `ticket-validation`, `door-incident-response`.
- **Experiencia:** simulación de puerta con estados, feedback inmediato y guía rápida siempre
  accesible.
- **Didact:** `simulation-lab`, `branching-scenario`, `flashcard`, `hint-reveal`.

### 7. Operación cashless: producto, catálogo y estación

- **Audiencia:** equipo GoFun/cashless.
- **Resultado:** mantener el orden de dependencias, configurar métodos de pago y revisar que
  un terminal apunta al evento y estación correctos.
- **Competencias:** `cashless-configuration`, `catalog-dependencies`, `terminal-provisioning`.
- **Experiencia:** constructor de flujo, simulación del panel y diagnóstico de configuración.
- **Didact:** `concept-map`, `sort`, `simulation-lab`, `rubric`.

### 8. Pulseras, identificadores e importaciones

- **Audiencia:** operación cashless.
- **Resultado:** preparar un CSV válido, vincular identificadores y detectar filas anómalas
  antes de importar.
- **Competencias:** `tag-import`, `csv-validation`, `access-group-mapping`.
- **Experiencia:** tabla editable, clasificación de errores y revisión previa a la acción.
- **Didact:** `data-explorer`, `categorize`, `rubric`.

### 9. Diagnóstico de dispositivos y kioscos

- **Audiencia:** soporte técnico.
- **Resultado:** separar fallos de energía, red, software, permisos y periféricos; recoger
  evidencia antes de escalar.
- **Competencias:** `hardware-triage`, `connectivity-diagnosis`, `safe-escalation`.
- **Experiencia:** árbol de decisión, anotación de fotografías y checklist de seguridad.
- **Didact:** `branching-scenario`, `evidence-annotation`, `hotspot`, `hint-reveal`.

### 10. Pagos, estados y devoluciones

- **Audiencia:** soporte de pagos y responsables autorizados.
- **Resultado:** interpretar el estado de una orden, encontrar la información relevante y
  decidir si consultar, reembolsar o escalar.
- **Competencias:** `payment-state-analysis`, `refund-safety`, `payment-escalation`.
- **Experiencia:** casos con línea temporal de estados y datos sintéticos; nunca credenciales
  ni operaciones reales.
- **Didact:** `timeline-steps`, `data-explorer`, `branching-scenario`, `rubric`.

### 11. Atención operativa con RAG

- **Audiencia:** transversal.
- **Resultado:** formular una consulta precisa, verificar la fuente y convertir una respuesta
  en una acción segura.
- **Competencias:** `knowledge-retrieval`, `source-verification`, `operational-judgement`.
- **Experiencia:** búsquedas sobre situaciones reales, contraste de fuentes y explicación de
  por qué una respuesta es suficiente o debe escalarse.
- **Didact:** `evidence-annotation`, `self-explanation-prompt`, `rubric`.

## Personalización útil

La personalización debe cambiar la actividad y el contexto, no solo el tono:

- **Rol:** un organizador practica autonomía; soporte practica diagnóstico y escalado.
- **Plataforma activa:** el mismo objetivo selecciona capturas, vocabulario y restricciones
  compatibles con Vivetix, Pretix, Crocantickets, Live o GoFun.
- **Experiencia previa:** una persona nueva recibe mapa, ejemplo y pistas; una experimentada
  entra en excepciones y decisiones de riesgo.
- **Momento de uso:** modo aprendizaje, práctica guiada o consulta urgente.
- **Preferencias:** imágenes o demostraciones se usan cuando hay un asset autorizado y aporta
  evidencia; no se inventan pantallas.

El conocimiento fuente sigue siendo la verdad. El perfil solo define intención, selección y
profundidad. OpenUI compone la pantalla en el momento con un shortlist compatible.

## Disponibilidad de componentes

Los 34 componentes de Didact pueden ser descubiertos, pero no todos deben emitirse todavía.
Este perfil usa dos horizontes:

- **Utilizable ahora:** `worked-example`, `timeline-steps`, `flashcard`, `hint-reveal`,
  `concept-map`, `data-explorer`, `self-explanation-prompt`, `rubric` y
  `evidence-annotation`, con los contratos y puertos ya disponibles cuando corresponda.
- **Objetivo de siguiente ola:** `branching-scenario`, `simulation-lab`, `hotspot`,
  `label-diagram`, `matching`, `sort`, `categorize` y preguntas evaluadas. Requieren adapters
  de runtime, assets o evaluación servidor-side; no deben fingirse con contenido estático.

El caso de ticketing es una buena prueba de aceptación para esa siguiente ola porque exige
decisiones, interfaces y diagnóstico, no únicamente texto y test.

## Estrategia de ingesta

Antes de generar cursos se necesita un paso declarativo y auditable:

1. inventariar y calcular duplicados;
2. asignar `audience`, `platform`, `task`, `content_kind`, `freshness` y `sensitivity`;
3. excluir binarios ejecutables y secretos;
4. detectar versiones canónicas y archivar las superadas;
5. aplicar OCR a recursos sin texto y transcribir vídeos;
6. separar fragmentos de procedimiento, referencia, política y solución de incidencias;
7. validar con una persona responsable los pasos con efecto real.

Las políticas y manuales completos permanecen consultables por RAG, pero solo originan cursos
cuando existe una conducta observable que practicar.

## Riesgos y datos pendientes

- **Secretos en documentos:** se observaron credenciales y enlaces operativos en texto claro.
  Deben rotarse fuera de este trabajo y excluirse de cualquier fixture, embedding o prompt.
- **Datos personales y de cliente:** hace falta un clasificador/redactor previo a la ingesta.
- **Versionado:** hay documentos duplicados y variantes `v1`, `v2`, `v3` sin metadatos
  consistentes; falta declarar cuál es vigente y quién la mantiene.
- **Tres PDF sin texto extraíble:** necesitan OCR o tratamiento visual específico.
- **Vídeos:** requieren transcripción y capítulos antes de ser fuente trazable.
- **Acciones irreversibles:** publicar, devolver, cambiar tarifas o configurar producción debe
  practicarse con datos sintéticos y confirmación explícita.
- **Criterios de competencia:** los porcentajes no bastan por sí solos. Cada competencia debe
  asociarse a evidencia: completar una configuración de prueba, explicar una decisión o
  resolver un escenario con límites definidos.
- **Fuentes externas:** manuales de fabricantes y plataformas pueden cambiar; requieren fecha
  de revisión y enlaces a la autoridad correspondiente.

## Primera validación recomendada

Crear tres rutas pequeñas con las mismas fuentes y perfiles distintos:

1. **Organizador nuevo:** cursos 1, 2, 3, 4 y 6.
2. **Operador de puerta:** cursos 1, 5, 6 y 9.
3. **Soporte interno experimentado:** diagnóstico corto de entrada y cursos 7, 8, 9 y 10.

Medir cobertura de pasos críticos, decisiones con evidencia, variedad de acciones,
dependencia de pistas, tasa de fallback, latencia y cambio causal entre perfiles. La prueba
de éxito no es producir más pantallas, sino que cada ruta permita hacer mejor el trabajo y
consultar la fuente cuando sea necesario.

## Alcance de la revisión de fuentes

Se recorrió el árbol completo y se extrajo texto de los 64 PDF y de documentos DOCX
representativos. Se revisaron en detalle las guías de promotores, invitaciones, consulta de
ventas, taquilla, control de acceso, panel GoFun, configuración de PAX, prerrecarga, Live,
kioscos, Paylands y procedimientos internos de eventos, ubicaciones, importación y hardware.
También se inspeccionó visualmente una muestra de manuales de organizador, invitaciones y
operación GoFun. No se ejecutaron instaladores ni se importaron credenciales o datos reales.
