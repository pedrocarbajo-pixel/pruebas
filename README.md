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

## Nivel de la tarea: estándar o extremo

Para casos críticos (cuantía o riesgo muy elevados) puede activarse el **nivel extremo** (`--nivel extremo` o el selector de la web, que pide confirmación). En ese nivel:

| Miembro | Estándar | Extremo |
|---|---|---|
| Claude | `claude-opus-5-5` | `claude-opus-5-5`, razonamiento adaptativo, esfuerzo `max` → `xhigh` → `high`, hasta 64 000 tokens de salida |
| ChatGPT | `gpt-6.1-sol` (reserva: `gpt-6-sol`, `gpt-5`) | `gpt-6-astra` (reserva: `gpt-6.1-sol`, `gpt-5.5-pro`), esfuerzo `max` → `xhigh` → `high` |
| Perplexity | `sonar-pro` (reserva: `fast`) | `high`, investigación profunda (reserva: `low`, `sonar-pro`), esfuerzo `xhigh` → `high`, búsqueda con contexto amplio |

- Si la API de un proveedor rechaza un nivel de esfuerzo, se prueba automáticamente el siguiente inferior, y el informe indica el modelo y el esfuerzo **efectivamente** utilizados.
- Los miembros reciben además instrucciones de máximo rigor: todas las interpretaciones razonables, doble comprobación de citas y escenarios de peor caso.
- Es notablemente más lento y costoso: úselo solo cuando el caso lo justifique.
- Los modelos se definen en `council/modelos.py` como **cadenas de reserva**: si la cuenta no tiene acceso a un modelo, se usa el siguiente y el informe lo indica («sustituye a … (no disponible)»).
- `council/modelos.py` se revisa cada 15 días para incorporar los modelos nuevos que publiquen los proveedores. Las variables `CLAUDE_MODEL`, `OPENAI_MODEL`, etc. de `.env` tienen prioridad: déjelas comentadas para recibir esas actualizaciones.

## Puesta en marcha en su ordenador

**Requisitos:** Python 3.10 o superior (en Windows, al instalarlo desde python.org, marque «Add python.exe to PATH») y, como mínimo, dos claves de API.

1. Descargue el proyecto (rama `claude/consejo-llm`) en una carpeta.
2. Ejecute el iniciador con doble clic o desde una terminal:
   - **Windows:** `iniciar.bat`
   - **macOS / Linux:** `./iniciar.sh`
3. La primera vez instala lo necesario y crea el archivo `.env`. Ábralo con un editor de texto, pegue sus claves (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`) y guárdelo.
4. Vuelva a ejecutar el iniciador. Comprobará cada proveedor con una llamada mínima y, si al menos dos responden, abrirá la aplicación en el navegador (`http://127.0.0.1:8000`).

Para detener la aplicación, cierre la ventana de la terminal o pulse Ctrl+C.

### Verificación manual

```bash
python -m council.verificar            # nivel estándar
python -m council.verificar --extremo  # comprueba también los modelos del nivel extremo
```

Cada línea indica `[ OK ]`, `[FALLO]` (con la causa probable y cómo resolverla) o `[ -- ]` (sin clave).

### Instalación manual (alternativa al iniciador)

```bash
pip install -r requirements.txt
cp .env.example .env      # rellene las claves; se cargan automáticamente al arrancar
```

## Interfaz web

```bash
python -m council.web     # abra http://127.0.0.1:8000
```

Permite escribir la tarea, adjuntar un documento (.txt, .md, .docx o .pdf), elegir el tipo de trabajo, los miembros y el presidente, y seudonimizar datos. Muestra el progreso de cada fase, el informe y botones para descargar el informe y el registro de auditoría.

**Progreso:** mientras el consejo trabaja, un indicador animado muestra la fase en curso, el tiempo transcurrido y una barra que avanza con cada entrega de los miembros.

**Versiones corregidas:** debajo del informe hay un campo «Solicitar una versión corregida». Escriba sus indicaciones (por ejemplo, «incorpora las citas concretas de la Ley del IRPF») y el presidente redactará una nueva versión completa a partir de los borradores y revisiones del consejo. Cada versión se guarda en un archivo propio (`_v2`, `_v3`…) y las anteriores quedan en el «Anexo III · Historial de versiones». Si la consulta se lanzó con seudonimización, las indicaciones también se seudonimizan.

**Seguridad:** el servidor no tiene autenticación y escucha solo en `127.0.0.1`. No lo exponga en una red sin colocar delante un proxy con autenticación y HTTPS. Las librerías de la página se sirven localmente, sin peticiones a CDN externas.

## Línea de órdenes

```bash
python -m council informe_tributario "Tributación en IRPF de la venta de un inmueble heredado en 2025" 
python -m council procedimiento_tributario "Analiza esta propuesta de liquidación y propone alegaciones" \
    --documento propuesta.pdf --seudonimizar
python -m council dictamen_juridico "Riesgo de derivación de responsabilidad al administrador" \
    --documento expediente.pdf --nivel extremo --seudonimizar
python -m council contrato_revisar "Revisa este contrato desde la posición del cliente" \
    --documento contrato.docx --miembros claude chatgpt --presidente chatgpt
```

## Resultados (`salidas/`)

- `informe_<fecha>_presidente.docx`: **informe del presidente en Word** (sin anexos), editable, con títulos, listas y tablas con formato real. Desde la web también puede descargarse en **PDF, HTML, Markdown o texto sin formato**; en la línea de órdenes, con `--formatos docx pdf html md txt`.
- `informe_<fecha>.md`: síntesis final y anexos con borradores y revisiones.
- `registro_<fecha>.json`: registro completo de la deliberación, para auditoría.
- `mapa_registro_<fecha>.json` (solo al seudonimizar): correspondencia entre marcadores y datos reales. **Custódielo** como información confidencial.

## Búsqueda web y normas recientes

Los modelos tienen una fecha de corte de conocimientos: no conocen normas publicadas después. Por eso los **tres miembros** pueden buscar en internet (`BUSQUEDA_WEB=1`), limitados a los dominios de `BUSQUEDA_DOMINIOS` (por defecto, fuentes oficiales: BOE, CENDOJ, AEAT, DGT, EUR-Lex…). Cada respuesta incluye la lista de fuentes consultadas. Si un proveedor rechaza la búsqueda, el miembro continúa sin ella y el informe lo indica.

Para normas muy recientes o críticas, lo más fiable es **adjuntar su texto oficial** (PDF del BOE) como documento: tiene prioridad sobre lo que los modelos sepan.

## Perplexity

- Usa la Agent API (`responses.create`) del SDK oficial `perplexityai` con el *preset* `PERPLEXITY_PRESET` (por defecto, `sonar-pro`).
- Su búsqueda se limita a los dominios de `BUSQUEDA_DOMINIOS`, igual que la de los demás miembros.
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
