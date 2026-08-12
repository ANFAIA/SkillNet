# Preferencias explícitas: contrato de aceptación y experimento

**Fecha:** 2026-08-11  
**Estado:** vertical v1 integrada; contrato de regresión y guía para los siguientes experimentos.  
**Alcance:** preferencias editables, caché compartida, pinning y OpenUI generado *on the fly*.

La interfaz, persistencia, proyección segura, prompts y partición de caché descritos aquí están
integrados. El planificador por capacidades continúa en sombra: observa y explica decisiones, pero
OpenUI sigue generando la pantalla real *on the fly*. Los casos relativos a un productor de imagen
o a «Aplicar también aquí» permanecen como criterios para la siguiente fase, no como funcionalidad
ya disponible.

## 1. Decisión de producto

Guardar una preferencia no muta una pantalla que la persona ya está leyendo. El render abierto
permanece fijado para conservar posición, respuestas y modelo mental. La nueva preferencia se usa:

1. en el siguiente nodo que todavía no tenga un render fijado;
2. al volver a seleccionar deliberadamente la experiencia del nodo actual;
3. nunca reescribiendo una fila compartida que otra persona pueda estar viendo.

«Aplicar mis nuevas preferencias» y «generar otra versión aunque nada haya cambiado» son operaciones
distintas. La primera ignora el pin antiguo, recalcula la clave y **sí reutiliza** un render compatible
de caché. La segunda es el `force` actual: busca variación deliberada y puede crear una fila salada.

```text
guardar ajustes
  -> render abierto: permanece idéntico
  -> siguiente nodo: calcula bundle nuevo
  -> reseleccionar nodo actual: ignora pin, admite cache hit y vuelve a fijar
  -> forzar otra versión: genera una variante y conserva historial
```

La interfaz debe explicar esta estabilidad: «Se aplicará a las próximas lecciones» y, cuando haya
una abierta, ofrecer «Aplicar también aquí». No debe sustituir contenido silenciosamente.

## 2. Bundle y clave

El bundle de preferencias es cerrado, versionado, no identificativo y canónico. En la primera
iteración contiene al menos los ejes que pueden alterar una experiencia:

- presentación solicitada;
- nivel de detalle;
- tratamiento de imágenes.

El nombre exacto de los campos pertenece al contrato backend. Estas invariantes no dependen de él:

1. el mismo bundle normalizado produce siempre el mismo bucket y la misma `cache_key`;
2. cambiar cualquiera de los tres ejes produce otro bucket y otra clave;
3. orden de claves JSON, valores omitidos equivalentes y representación enum/string no crean
   buckets distintos;
4. `user_id`, `memory_md`, rol libre y eventos crudos no entran en el bundle;
5. dos personas del mismo bucket comparten render; personas de buckets incompatibles no;
6. versión de proyección, política, catálogo y prompt invalidan sus decisiones respectivas;
7. un bundle vacío conserva el comportamiento y las claves heredadas hasta que la migración decida
   explícitamente lo contrario.

La opción segura inicial es particionar por el bundle declarado completo. Optimizar para que una
preferencia solo invalide nodos compatibles requiere resolver capacidades antes del lookup de
caché; no se hará deduciendo compatibilidad después de servir una fila.

## 3. Concurrencia y pinning

Un cambio de preferencias mientras existe una generación en vuelo no puede terminar fijando la
variante anterior como si fuera la nueva. La petición debe transportar una revisión o fingerprint.
Al persistir:

- si sigue vigente, el render se fija normalmente;
- si cambió, el render puede conservarse en su bucket compartido, pero no se fija a esa persona;
- el cliente solicita o adopta la variante correspondiente al bundle vigente.

Cancelar procesos en memoria es una optimización, no la garantía: no cubre varios workers ni una
finalización simultánea. La comprobación de revisión al fijar es la protección determinista.

## 4. Matriz de aceptación

### 4.1 Funciones puras y caché

| ID | Nivel | Caso | Resultado obligatorio |
|---|---|---|---|
| K01 | unit | mismo bundle construido dos veces | mismo bucket y misma clave |
| K02 | unit | cambia solo presentación | cambia bucket y clave |
| K03 | unit | cambia solo detalle | cambia bucket y clave |
| K04 | unit | cambia solo imágenes | cambia bucket y clave |
| K05 | unit | cambia el orden de claves JSON | mismo bucket |
| K06 | unit | bundle vacío/ausente en perfil legado | comportamiento legado definido |
| K07 | unit | cambia `projection_version` | cambia clave |
| K08 | unit | cambia `policy_version` | cambia clave |
| K09 | unit | cambia catálogo o prompt | cambia clave |
| K10 | unit | dos `user_id` con el mismo bundle | misma clave; la identidad no es entrada |
| K11 | unit | preferencia declarada durante calibración | se conserva; solo se suprime la inferida |
| K12 | unit | valor libre o desconocido | rechazo de validación, nunca bucket improvisado |

### 4.2 Selección, caché y estabilidad

| ID | Nivel | Caso | Resultado obligatorio |
|---|---|---|---|
| S01 | service | hay pin y no cambió el bundle | devuelve exactamente el pin, sin recalcular |
| S02 | service | se guardan ajustes con pantalla abierta | `GET` sigue devolviendo los mismos bytes |
| S03 | service | siguiente nodo tras cambiar bundle | usa la clave nueva |
| S04 | service | reselección del nodo actual | omite pin viejo pero admite cache hit nuevo |
| S05 | service | otro usuario ya generó el bundle nuevo | reselección reutiliza esa fila; cero LLM |
| S06 | service | volver al bundle anterior | reutiliza la fila compartida original |
| S07 | service | `force=true` sin cambiar bundle | crea/adopta una variante de historial según contrato actual |
| S08 | service | cambio mientras genera el bundle viejo | el resultado viejo no se fija como vigente |
| S09 | service | usuario A cambia bundle | no altera pin ni fila servida al usuario B |
| S10 | service | preferencia sin componente compatible | render válido y código de fallback cerrado |

### 4.3 OpenUI y experiencia completa

| ID | Nivel | Caso | Resultado obligatorio |
|---|---|---|---|
| E01 | E2E | preferencia visual + capacidad compatible | componente visual alcanzable desde `root` |
| E02 | E2E | preferencia de imagen + asset/productor disponible | referencia tipada, procedencia y texto alternativo |
| E03 | E2E | imagen no disponible o productor falla | fallback OpenUI válido; no pantalla rota ni dato inventado |
| E04 | E2E | preferencia visual en nodo crítico | hechos, aviso, práctica y evaluación permanecen |
| E05 | E2E | dos usuarios, mismo bundle | segundo POST es cache hit y no añade llamadas LLM/media |
| E06 | E2E | dos bundles incompatibles | no comparten el programa equivocado |
| E07 | E2E | guardar ajuste con nodo abierto | contenido no cambia hasta acción o navegación explícita |
| E08 | E2E | pulsar «Aplicar también aquí» | nuevo bucket o cache hit; versión anterior sigue en historial |
| E09 | E2E | componente inaccesible para el perfil | se filtra antes de ranking y se elige alternativa operable |
| E10 | E2E | render dinámico | sigue pasando parser, gate y serialización OpenUI; nunca HTML libre |

## 5. Experimento A/B reproducible

### Pregunta

¿Una preferencia explícita produce una diferencia observable y estable sin contaminar caché,
objetivo, seguridad ni evaluación?

### Diseño

- Un nodo con objetivo, fuente, criticidad y versión idénticos.
- Dos bundles; cambia una sola variable:
  - A: presentación equilibrada, detalle estándar, imágenes automáticas.
  - B: presentación visual, detalle estándar, imágenes preferidas.
- Dos perfiles sintéticos por bundle para comprobar reutilización.
- Dos repeticiones de generación por condición cuando no haya cache hit.
- Modelo, prompt, catálogo, seed y temperatura congelados.
- Ejecutar primero con un nodo compatible con imagen y después con uno incompatible.

### Secuencia

```text
1. Generar A1 y registrar key, llamadas, plan, ui_spec y hechos obligatorios.
2. Solicitar A2: debe adoptar el mismo render desde caché.
3. Abrir A1 y cambiar su bundle a B: GET debe seguir mostrando A.
4. Abrir un nodo nuevo con B: debe usar una key distinta y seleccionar B.
5. Reseleccionar el nodo original: debe admitir cache hit B o generar B una sola vez.
6. Solicitar B2: debe reutilizar B.
7. Volver A1 a A: debe reencontrar la fila A, no regenerarla.
8. Repetir 1-7 en el nodo incompatible y comprobar fallback explícito.
```

### Evidencia a guardar

Por solicitud:

- bundle normalizado y fingerprint, nunca identidad;
- `cache_key`, `cached`, `render_id` y número de llamadas por productor;
- `PlanTrace` interno y proyección pública mínima de cumplimiento/fallback;
- tipos alcanzables desde `root`;
- referencias a hechos y seguridad preservados;
- latencia, tokens, coste de media, fallback y errores de validación.

### Criterios de éxito

- K01-K12 y S01-S10 pasan;
- A y B nunca comparten una clave incompatible;
- el segundo perfil de cada bundle cuesta cero generación;
- cambiar ajustes no modifica la pantalla abierta;
- aplicar los ajustes al nodo actual reutiliza caché cuando existe;
- una imagen solicitada aparece cuando es compatible o devuelve una razón cerrada;
- objetivo, hechos críticos, feedback y evaluación son equivalentes entre A y B;
- 100 % de componentes contados son alcanzables y la UI pasa el gate a la primera o degrada de
  forma explícita.

### Decisión tras el experimento

- **Activar:** cumple todos los invariantes y mejora preferencia/acción sin regresión crítica.
- **Repetir:** diferencia pedagógica incierta, pero caché, seguridad y contrato son correctos.
- **Revertir:** fuga entre buckets, pin mutado, carrera de revisión, hechos omitidos o fallback roto.

## 6. Orden recomendado de automatización

1. K01-K12 como pruebas puras del bundle y la clave.
2. S01-S10 con repositorios y productores falsos; ninguna red.
3. E01-E10 con fixture OpenUI y un productor de imagen determinista.
4. A/B con proveedor real, límites de coste y artefactos versionados.

Las tres primeras capas bloquean el despliegue. El A/B con proveedor aprende sobre calidad y coste;
no sustituye los contratos deterministas.
