# Consejo de LLM (Claude + ChatGPT)

Herramienta de línea de órdenes que somete una tarea compleja o sensible (por ejemplo, redactar o revisar un contrato) a un **consejo** formado por Claude (Anthropic) y ChatGPT (OpenAI).

## Cómo delibera el consejo

| Fase | Qué ocurre |
|---|---|
| 1 · Borradores independientes | Ambos modelos resuelven la tarea en paralelo, sin ver la respuesta del otro. |
| 2 · Revisión cruzada | Cada modelo revisa críticamente la respuesta anonimizada del otro: errores, omisiones, discrepancias y nota de 1 a 10. |
| 3 · Síntesis | El presidente (Claude por defecto) integra todo con los autores anonimizados y entrega: respuesta final, consensos, **discrepancias**, cuestiones que requieren verificación humana y nivel de confianza. |

Cada ejecución hace 5 llamadas a las API (2 borradores + 2 revisiones + 1 síntesis).

## Instalación

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
# Opcional: elegir modelos (compruebe los identificadores vigentes de cada proveedor)
export CLAUDE_MODEL=claude-opus-5-5
export OPENAI_MODEL=gpt-5
```

## Uso

```bash
# Revisar un contrato (.txt, .md, .docx o .pdf), seudonimizando datos personales
python -m council revisar "Revisa este contrato de prestación de servicios desde la posición del cliente" \
    --documento contrato.docx --seudonimizar

# Redactar un contrato
python -m council redactar "Redacta un acuerdo de confidencialidad mutuo entre dos sociedades españolas, ley y fuero españoles"

# Tarea general, con ChatGPT como presidente
python -m council general "Analiza los riesgos de esta operación" --presidente chatgpt
```

Resultados en `salidas/`:

- `informe_<fecha>.md`: síntesis final y anexos con borradores y revisiones.
- `registro_<fecha>.json`: registro completo de la deliberación, para auditoría.
- `mapa_registro_<fecha>.json` (solo con `--seudonimizar`): correspondencia entre marcadores y datos reales. **Custódielo** como información confidencial.

## Seudonimización (`--seudonimizar`)

Sustituye antes del envío DNI, NIE, CIF, IBAN, correos electrónicos y teléfonos españoles por marcadores (`[DNI_1]`, `[IBAN_1]`…) y los restaura en el informe local. **No detecta nombres propios ni direcciones**: revise el documento antes de enviarlo si contiene información especialmente sensible.

## Advertencias

- El resultado es un **borrador de apoyo**; debe revisarlo un profesional cualificado antes de usarlo.
- Los documentos se envían a Anthropic y a OpenAI. Compruebe que sus condiciones de tratamiento de datos son compatibles con sus obligaciones de confidencialidad y con el RGPD.
- Que dos modelos coincidan no garantiza que la respuesta sea correcta: ambos pueden compartir el mismo error.

## Pruebas

```bash
python -m pytest
```

Las pruebas usan miembros simulados y no realizan llamadas a las API.
