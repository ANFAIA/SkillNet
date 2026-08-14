# Informe de ronda

- Perfiles: 5
- Recorridos: 15
- Pantallas: 45
- Errores: 0

## Formatos

| Formato | Cantidad |
|---|---:|
| explanation | 30 |
| mixed | 15 |

## Componentes

| Componente | Cantidad |
|---|---:|
| `Flashcard` | 45 |
| `Stack` | 45 |
| `StepSequence` | 45 |
| `TextContent` | 45 |

## Señales de calidad

- Pantallas con concepto + QuizItem: 0 (0.0)
- Caracteres visibles mín./media/máx.: 626 / 980.8 / 1102
- Similitud media entre brazos: 0.6908
- Similitud media dentro del mismo brazo: 0.7103

## Métricas por perfil

| Perfil | Experiencia | Modalidad | Bloques cortos | Recorridos | Pantallas | Media caracteres | Caché inicial | Duración media (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| base | none | balanced | false | 3 | 9 | 952.9 | 0 | 27.25 |
| experience | experienced | balanced | false | 3 | 9 | 1015.7 | 0 | 29.25 |
| short-blocks | none | balanced | true | 3 | 9 | 1008.0 | 0 | 25.88 |
| textual | none | text | false | 3 | 9 | 950.8 | 0 | 27.313 |
| visual | none | visual | false | 3 | 9 | 976.8 | 0 | 25.812 |

## Interpretación

- La ronda tiene tres repeticiones forzadas por brazo; ninguna petición inicial usó caché.
- La estructura es más informativa que la prosa: el muestreo puede cambiar texto sin efecto del perfil.
- Todos los brazos usaron la misma receta de componentes en todas las pantallas; no hubo personalización estructural.
- Bloques cortos no redujo la longitud media frente al perfil base y falló su comprobación direccional.
- La ausencia de QuizItems impide obtener evidencia sobre errores, mastery o replanificación.

