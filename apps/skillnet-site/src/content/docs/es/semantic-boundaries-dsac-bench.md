---
title: "Banco DSAC"
order: 53
section: "research"
group: "semantic-boundaries"
---

# DSAC-Bench: Benchmark de Clasificación de Sensibilidad y Acceso de Documentos

## Motivación

No existe un benchmark público para la clasificación de acceso/sensibilidad de documentos. Los benchmarks de clasificación de texto existentes (AG News, 20Newsgroups, MTEB) miden tema, sentimiento o intención, nunca nivel de acceso. El único dataset del mundo real con etiquetas de acceso es el corpus de cables diplomáticos de WikiLeaks (Alzhrani et al., UC Colorado Springs), con disponibilidad limitada.

Este vacío hace que las cifras de precisión publicadas para sistemas de clasificación de acceso sean incomparables. DSAC-Bench está diseñado para llenar ese vacío.

## Estructura

### 4 Niveles de Acceso (alineados con ISO 27001)

| Nivel | Código | Ejemplo |
|-------|------|---------|
| Público | PUB | FAQ del sitio web |
| Interno | INT | Manual de procesos |
| Confidencial | CONF | Contrato con proveedor |
| Restringido | REST | Actas del consejo con datos personales |

### 8 Dominios

1. **Catering/Eventos:** fácil (vocabulario muy distinto entre niveles)
2. **Legal/Bufete de abogados:** muy difícil (vocabulario uniforme entre niveles)
3. **Clínico/Salud:** difícil (la señal está en los PII, no en el tema)
4. **Tecnología/Startup:** medio-alto (README vs informe de vulnerabilidad)
5. **Educación:** medio (programa de estudios vs expediente de alumno)
6. **Administración Pública:** alto (transparencia vs reservado)
7. **Finanzas/Banca:** alto (regulación MiFID, información privilegiada)
8. **Recursos Humanos:** medio-alto (nóminas, evaluaciones, políticas)

### 7 Divisiones Funcionales

| División | Abrev. | Propósito | Dificultad |
|-------|--------|---------|------------|
| Core | CORE | Documentos típicos de cada nivel/dominio | Fácil-Medio |
| Adversarial de Mismo Tema | STA | Mismo tema, distinto nivel (4 versiones) | Difícil |
| Señal Mínima | MINSIG | 1-3 frases, señal mínima | Difícil |
| Cross-Domain | XDOM | Entrenar en A, evaluar en B | Medio-Difícil |
| Temporal | TEMP | Mismo documento, políticas que cambian con el tiempo | Difícil |
| Ruidoso | NOISE | Errores de OCR, jerga, fragmentos | Medio |
| Variable en Escala | SCALE | De 1 frase a 5 páginas | Medio |

### Volumen

| División | Docs/dominio | Dominios | Total |
|-------|-------------|---------|-------|
| CORE | 160 | 8 | 1.280 |
| STA | 80 | 8 | 640 |
| MINSIG | 40 | 4 | 160 |
| TEMP | 20 | 4 | 80 |
| NOISE | 40 | 4 | 160 |
| SCALE | 40 | 4 | 160 |
| **Total** | | | **~2.480** |

## Métricas

### Métricas Principales

- **Macro F1.** Estándar del campo
- **WSE (Weighted Security Error, Error de Seguridad Ponderado).** Métrica novedosa que penaliza asimétricamente los errores graves
- **Recall REST.** Cuántos documentos restringidos escapan

### Matriz de Costes WSE

```
              Predicted ->
              PUB   INT   CONF  REST
Real    PUB  [ 0     1     2     3  ]
        INT  [ 3     0     1     2  ]
        CONF [ 6     3     0     1  ]
        REST [ 10    6     3     0  ]
```

REST->PUB = 10 (daño máximo: documento restringido clasificado como público).
PUB->INT = 1 (molestia menor: documento público requiere autorización interna).

### DSAC-Score (Agregado)

```
0.30 x F1_CORE + 0.30 x F1_STA + 0.15 x (1-WSE/10) + 0.10 x F1_NOISE
    + 0.10 x (1-CrossGap) + 0.05 x F1_SCALE
```

## Protocolo de Generación

1. **Gold standard manual:** 192 documentos (2-3 por celda dominio x nivel)
2. **Generación sintética:** 3 LLMs diferentes (40% DeepSeek, 30% Claude, 30% GPT-4o)
3. **Validación cruzada:** el LLM verificador es distinto del LLM generador
4. **Validación humana:** 3 anotadores, mínimo 30% de los documentos (~750)
5. **Anti-sesgo:** test de detección de modelo, documentos "troyanos"

## Modos de Evaluación

- **Modo A (zero-shot):** solo recibe descripciones de nivel, sin datos etiquetados
- **Modo B (supervisado):** recibe 640 de entrenamiento + 128 de desarrollo de la división CORE

## Primeros Resultados (División Core, 1.280 docs)

```
ZERO-SHOT (ontology):       53.1% accuracy | F1 0.523 | WSE 1.70 | GER 23.0% | DSAC 0.575
SVM LODO (cross-domain):    78.2% accuracy | F1 0.784 | WSE 0.56 | GER  4.6% | DSAC 0.839
SVM INTRA (5-fold):          93.2% accuracy | F1 0.932 | WSE 0.20 | GER  2.1% | DSAC 0.939
```

### Precisión por Dominio (SVM LODO)

| Dominio | Precisión |
|--------|----------|
| Legal | 90.6% |
| RRHH | 84.4% |
| Catering | 81.2% |
| Admin | 78.1% |
| Educación | 75.0% |
| Finanzas | 75.0% |
| Clínica | 71.2% |
| Tecnología | 70.0% |

### Resultados de Fine-Tuning (3 épocas, MiniLM 384d)

- LODO con fuga de datos: 100%, NO FIABLE (los embeddings vieron datos de test)
- **Test de holdout (160 docs nuevos nunca vistos):** KNN 84.4% (+12.5pp vs base), SVM 84.4% (+2.5pp)
- **Aprendizaje real confirmado.** No es memorización. GER cae del 15% al 5% (3x menos errores graves)
- Dominio legal: 95 -> 100% con fine-tuning. El dominio más difícil MEJORA.

## Comparación con el Benchmark de WikiLeaks

El único otro dataset con etiquetas de acceso reales:

| Método | Precisión | F1 | Dataset |
|--------|----------|-----|---------|
| RAC (Chang et al., 2026) | ~96% | ~94% | Cables de WikiLeaks |
| Fine-tuning supervisado | — | 90% | Cables de WikiLeaks |
| Nuestro SVM + e5-large (sintético) | 100% | ~100% | DSAC-Bench intra-dominio |
| Nuestro SVM LODO | 78.2% | 0.784 | DSAC-Bench cross-domain |

La comparación no es directa: los cables de WikiLeaks son documentos diplomáticos reales donde CONFIDENCIAL y NO CLASIFICADO pueden hablar del mismo tema (por ejemplo, relaciones con Rusia). Nuestros datos sintéticos con vocabulario distinto por nivel hacen que la tarea intra-dominio sea más fácil. El resultado cross-domain de LODO (78.2%) es un reflejo más honesto de la dificultad en el mundo real.
