# Modo degradado: exponerlo en la interfaz

**Estado:** plan (no implementado, salvo lo indicado en §2)
**Relacionado:** [`media-artifacts.md`](media-artifacts.md) §5,
[`personalization.md`](personalization.md) §4, [`backend-api.md`](backend-api.md),
[`configuration.md`](configuration.md), `README.md` §"Audio, images and the render cache"

> SkillNet degrada de formas concretas cuando faltan claves externas (ElevenLabs / OpenRouter)
> o el proveedor devuelve errores de cuota. Hoy esas degradaciones son **invisibles** para
> admin y aprendices, lo que confunde ("¿por qué la voz es robótica?", "¿por qué no hay
> imagen?", "¿por qué el altavoz no suena?"). Este documento es el plan para hacerlas visibles
> y no-alarmantes, sin implementar la UI (salvo §2, ya resuelto en código).

## 0. Los tres estados degradados a comunicar

Verificados contra el código (ver `media-artifacts.md` §5):

1. **TTS sin clave/crédito → voz del mascota falla en duro (500).** `POST /api/v1/tts/synthesize`
   (`src/routes/tts.py`) no cae al proveedor offline; `ElevenLabsProvider.synthesize` lanza en
   no-200 (`src/services/tts_service.py`). Es un **hueco conocido**.
2. **TTS sin clave/crédito → podcast en voz offline (eSpeak).** El podcast sí degrada por la
   cadena `ElevenLabs → Azure → eSpeak NG` (`src/services/media/podcast/voices.py`), pero suena
   robótico.
3. **OpenRouter sin clave → infografía sin póster.** `generate_image`
   (`src/services/media/images.py`) es best-effort; la infografía sale con `has_image=false`.

Todo esto se **hornea en el seed** y se comparte entre aprendices, así que el mensaje correcto
es a nivel de **deployment/admin**, no por-usuario.

## 1. Banner / indicador de salud de medios (admin)

**Dónde.** Backend: ampliar `GET /health` (`src/routes/health.py`) — o añadir
`GET /api/v1/settings/media-status` si se prefiere separar lo público de lo autenticado.
Frontend: consumir en `src/api/health.ts` (`HealthRead`) y renderizar en la página de admin
`src/pages/admin/Settings.tsx`, que **ya tiene el patrón exacto**: hoy muestra una sola línea
de aviso cuando no hay modelo LLM configurado. El indicador de medios es la misma idea.

**Backend — la forma mínima.** Añadir a la respuesta de `/health` un bloque `media` derivado
**solo de configuración** (sin llamar a proveedores):

```jsonc
"media": {
  "tts": { "provider": "elevenlabs", "configured": true, "live_voice_fallback": false },
  "images": { "configured": false }
}
```

- `tts.configured` = `settings.TTS_PROVIDER != "disabled"` y `settings.TTS_API_KEY` no vacío
  (o `provider == "offline"`). Reutiliza `tts_is_available` de `src/personalization/modality.py`.
- `tts.live_voice_fallback = false` documenta el hueco: **la voz en vivo no tiene red de
  seguridad offline** aunque el podcast sí.
- `images.configured` = `bool(settings.OPENROUTER_API_KEY)` o que `IMAGE_MODEL` no sea
  `openrouter/*` (entonces usa `LLM_API_KEY`).

Detección de **cuota agotada** (opcional, fase 2): un contador de errores 429/402 por proveedor
en memoria de proceso (misma suposición single-worker que `_INFLIGHT` en
`node_render_service.py`), expuesto como `"quota_exhausted": true`. La v1 se queda en
"configurado / no configurado", que ya cubre el 90% de la confusión.

**Frontend — la forma mínima.** En `Settings.tsx`, junto al aviso de modelo, un `SettingRow`
(o un banner discreto arriba) que solo aparece cuando algo está degradado. Mensajes:

- Sin TTS: *"El audio usará una voz offline básica (robótica) hasta que se añada una clave de
  ElevenLabs con crédito. La voz en vivo del mascota estará muda."*
- Sin imágenes: *"Las infografías se generarán sin póster hasta que se configure
  `OPENROUTER_API_KEY`."*

Sin degradación, no se muestra nada (misma disciplina que el resto de `Settings.tsx`).

## 2. Voz del mascota que degrada en silencio (YA IMPLEMENTADO)

**Dónde.** `src/components/mascota/MascotaCompanion.tsx`.

**Estado: ya correcto — no requiere cambios.** `speak()` lanza en `!res.ok`, y **todos** los
llamadores lo tragan (`void speak().catch(() => undefined)` en el auto-read y en
`handleToggleMute`). Un 500 de TTS no muestra error: el globo con el texto permanece y solo
falta el audio. Verificado en el componente actual.

**Mejora opcional (baja prioridad).** Cuando el health-status de §1 diga `tts.configured =
false`, **ocultar el icono de altavoz** en vez de dejar un botón que no hace nada. Sería:
pasar una prop `ttsAvailable` (desde el `useHealth()` de §1) a `MascotaCompanion` y envolver el
`<button>` de mute en `ttsAvailable && (...)`. El globo de texto se mantiene siempre. Es
puramente cosmético; el comportamiento ya es seguro.

## 3. Mención en el onboarding (condicional)

**Dónde.** `src/pages/onboarding/Onboarding.tsx` y el paso de preferencias de modalidad
(`src/components/onboarding/`, junto a `AccessibilityStep.tsx`).

**Qué.** El onboarding deja al aprendiz elegir preferencia audio/visual. Si `tts.configured =
false` (de §1), en el paso donde se ofrece "audio" añadir una nota inline: *"El audio está en
modo básico en esta instalación (voz offline)."* — para que elegir "audio" no genere una
expectativa que la instalación no puede cumplir. No bloquea la elección (la resolución de
modalidad ya degrada audio → texto vía `resolve_declared_modality`), solo informa.

**Prioridad.** La más baja de las tres: solo aporta si el deployment corre sin TTS y usa el
onboarding. Implementar después de §1.

## Orden de implementación sugerido

1. **§1 backend** — ampliar `/health` con el bloque `media` (barato, sin llamadas externas).
2. **§1 frontend** — banner condicional en `Settings.tsx` reutilizando `useHealth()`.
3. **§2 mejora opcional** — ocultar el altavoz del mascota cuando no hay TTS.
4. **§3** — nota en el onboarding.

Cada paso es independiente y no toca la generación ni el pipeline de medios; son todos
lecturas de configuración + render condicional.
