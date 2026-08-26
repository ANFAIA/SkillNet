---
title: "Fronteras semánticas"
order: 51
section: "research"
---

# Fronteras Semánticas

## El problema

En sistemas de IA que usan embeddings para búsqueda, dos documentos sobre el mismo tema pero con distintos niveles de acceso acaban cerca en el espacio vectorial. Una búsqueda semántica puede devolver el confidencial junto al público. Esto no es teórico. Microsoft Copilot fue vulnerado de esta forma (CVE-2026-42824).

## El experimento

Queríamos probar **hasta dónde se puede llegar clasificando niveles de acceso de documentos únicamente a partir del contenido, sin ninguna intervención humana.** La idea: usar embeddings para determinar si un documento es público, interno o confidencial, dejando que la máquina decida en función de lo que dice el texto.

Construimos un benchmark (DSAC-Bench: 1.280 documentos en 8 dominios) y ejecutamos más de 400 configuraciones (SVM, gradient boosting, entrenamiento domain-adversarial, costes asimétricos, IRM, y más). Dentro de un mismo dominio, funciona perfectamente (100% de precisión). Pero entre dominios, nada superó el **78.2%** de precisión. El techo es intrínseco.

## La conclusión

**La privacidad no es una propiedad del contenido. Es una decisión humana.** El mismo texto puede ser público o confidencial según la política organizativa. Una cláusula de responsabilidad en un contrato es pública en la biblioteca de plantillas de un despacho de abogados pero confidencial en un caso activo. Ninguna cantidad de NLP puede resolver esto porque la información sencillamente no está en el texto.

La conclusión actual es que clasificar el acceso solo a partir del contenido no tiene un camino viable hacia adelante. Varias direcciones merecen explorarse desde aquí:

- **Control de acceso estructural.** La organización decide qué va dónde (carpetas, contenedores, etiquetas), y el sistema hace cumplir esas fronteras. El humano toma las decisiones de acceso; la máquina se encarga de aplicarlas.
- **Grafos de conocimiento.** Usar la estructura del grafo en lugar del contenido para determinar el acceso. El paper G-SPEC mostró que el 68% de las ganancias de seguridad vienen del grafo, no del LLM.
- **Prefiltrado basado en vectores.** Embeddings binarios como primer paso rápido para acotar candidatos antes de aplicar reglas deterministas.
- **Clasificación híbrida.** Combinar el análisis de contenido con metadatos de procedencia y reglas de co-ocurrencia (el modelo de 3 ejes). El contenido solo tiene un techo del 78%, pero añadir unos pocos ejemplos etiquetados por humanos por dominio lo rompe.

Ninguna de estas está elegida todavía. El experimento mostró dónde están los límites; el siguiente paso es encontrar qué combinación funciona en la práctica.

Los detalles completos de qué se probó y qué se descubrió están en los documentos de abajo.

## Descubrimientos interesantes por el camino

- **La cuantización binaria mejora la precisión.** Se esperaba que reducir vectores de 1024 dimensiones a binario (0s y 1s) perdiera información. En cambio, actúa como un regularizador, aplanando el ruido mientras preserva la señal discriminante. Esto es contraintuitivo y potencialmente útil más allá del control de acceso.

- **Todo sistema que resuelve este problema en el mundo real usa 3 ejes, no 1.** NASA FDIR, compartimentación militar, clasificación nuclear: todos convergen de forma independiente en el mismo patrón de contenido + procedencia + reglas de combinación. Ningún sistema en producción depende únicamente del análisis de contenido.

- **5 ejemplos etiquetados por dominio rompen el techo.** El muro del 78% es solo para zero-shot. Con solo 5 ejemplos etiquetados por humanos en un dominio nuevo, la precisión salta al 80%+. La intervención humana no necesita ser exhaustiva, solo un pequeño anclaje.

- **Ghost Vectors.** Los embeddings borrados sobreviven en los índices HNSW. Investigadores demostraron una recuperación del 100% de datos de pacientes a partir de una base de datos vectorial que había "borrado" los registros. [arXiv:2606.18497](https://arxiv.org/abs/2606.18497)

- **G-SPEC.** Un enfoque neuro-simbólico para la aplicación de políticas encontró que el 68% de las ganancias de seguridad vienen de la estructura del grafo, no del LLM. [arXiv:2512.20275](https://arxiv.org/abs/2512.20275)

## Profundizaciones

- [Content-Based Classification](/docs/semantic-boundaries-classification). El descubrimiento central: contenido + procedencia + combinación, todo lo que se probó, evidencia de convergencia de campos independientes
- [experiments/dsac-bench.md](/docs/semantic-boundaries-dsac-bench). Diseño del benchmark DSAC-Bench (1.280 docs, 8 dominios)
- [experiments/experiment-log.md](/docs/semantic-boundaries-experiment-log). Tabla completa de los 46 experimentos
