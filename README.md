# Consejo de LLM (Claude + ChatGPT + Perplexity)

Herramienta que somete una tarea compleja o sensible —jurídica o tributaria— a un **consejo** formado por Claude (Anthropic), ChatGPT (OpenAI) y Perplexity (con búsqueda web y fuentes). Se usa desde una **interfaz web** sencilla o desde la línea de órdenes.

## Cómo delibera el consejo

| Fase | Qué ocurre |
|---|---|
| 1 · Borradores independientes | Cada miembro resuelve la tarea en paralelo, sin ver a los demás. Perplexity adjunta las fuentes web que ha consultado. |
| 2 · Revisión cruzada | Cada miembro revisa críticamente, sin conocer su autoría, las respuestas de los demás: errores, normas derogadas, citas no verificables, omisiones y nota de 1 a 10. |
| 3 · Síntesis | El presidente (Claude por defecto) integra todo con los autores anonimizados y entrega: respuesta final, consensos, **discrepancias**, fuentes citadas, cuestiones que requieren verificación humana y nivel de confianza. |

Con tres miembros, cada consulta hace 7 llamadas (3 borradores + 3 revisiones + 1 síntesis); con dos, 5.

## Tipos de trabajo

| Modo | Uso |
|---|---|
| `contrato_revisar` | Revisión cláusula por cláusula, tabla de riesgos, cláusulas ausentes e implicaciones fiscales. |
| `contrato_redactar` | Borrador completo con supuestos y datos `[PENDIENTE: …]`. |
| `dictamen_juridico` | Antecedentes, cuestiones, normativa, jurisprudencia, análisis y conclusiones. |
| `informe_tributario` | Impuestos afectados, normativa, consultas de la DGT, resoluciones del TEAC, cálculos paso a paso, riesgos y obligaciones formales. |
| `procedimiento_tributario` | Gestión, inspección, recaudación, sancionador o revisión: plazos, posibles defectos, alegaciones y recursos, y borrador de escrito. |
| `general` | Cualquier otra tarea compleja. |

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env      # rellene las claves y exporte las variables, p. ej.: set -a; . ./.env; set +a
```

Basta con dos de las tres claves; los miembros sin clave aparecen desactivados en la web.

## Interfaz web

```bash
python -m council.web     # abra http://127.0.0.1:8000
```

Permite escribir la tarea, adjuntar un documento (.txt, .md, .docx o .pdf), elegir el tipo de trabajo, los miembros y el presidente, y seudonimizar datos. Muestra el progreso de cada fase, el informe y botones para descargar el informe y el registro de auditoría.

**Seguridad:** el servidor no tiene autenticación y escucha solo en `127.0.0.1`. No lo exponga en una red sin colocar delante un proxy con autenticación y HTTPS. Las librerías de la página se sirven localmente, sin peticiones a CDN externas.

## Línea de órdenes

```bash
python -m council informe_tributario "Tributación en IRPF de la venta de un inmueble heredado en 2025" 
python -m council procedimiento_tributario "Analiza esta propuesta de liquidación y propone alegaciones" \
    --documento propuesta.pdf --seudonimizar
python -m council contrato_revisar "Revisa este contrato desde la posición del cliente" \
    --documento contrato.docx --miembros claude chatgpt --presidente chatgpt
```

## Resultados (`salidas/`)

- `informe_<fecha>.md`: síntesis final y anexos con borradores y revisiones.
- `registro_<fecha>.json`: registro completo de la deliberación, para auditoría.
- `mapa_registro_<fecha>.json` (solo al seudonimizar): correspondencia entre marcadores y datos reales. **Custódielo** como información confidencial.

## Perplexity

- Usa la Agent API (`responses.create`) del SDK oficial `perplexityai` con el *preset* `PERPLEXITY_PRESET` (por defecto, `sonar-pro`).
- Si define `PERPLEXITY_DOMINIOS`, su búsqueda se limita a esos dominios (en `.env.example` hay una lista de fuentes oficiales: BOE, CENDOJ, AEAT, DGT, EUR-Lex…).
- Las fuentes consultadas se añaden a su respuesta para que el resto del consejo las contraste.

## Seudonimización

Sustituye antes del envío DNI, NIE, CIF, IBAN, correos electrónicos y teléfonos españoles por marcadores (`[DNI_1]`, `[IBAN_1]`…) y los restaura en el informe local. **No detecta nombres propios ni direcciones.**

## Advertencias

- El resultado es un **borrador de apoyo**; debe revisarlo un profesional cualificado antes de usarlo.
- Los documentos se envían a Anthropic, OpenAI y Perplexity. Compruebe que sus condiciones de tratamiento de datos son compatibles con sus obligaciones de confidencialidad y con el RGPD.
- Que varios modelos coincidan no garantiza que la respuesta sea correcta.
- Verifique siempre la vigencia de las normas a la fecha de los hechos y los plazos con la fecha real de notificación.

## Pruebas

```bash
python -m pytest
```

Las pruebas usan miembros simulados y no realizan llamadas a las API.
