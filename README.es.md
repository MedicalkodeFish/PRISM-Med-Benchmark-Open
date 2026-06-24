# Benchmark PRISM-Med

**Idiomas:** [English](README.md) · [中文](README.zh-CN.md) · [Français](README.fr.md) · [Español](README.es.md)

**PRISM-Med es un benchmark multidimensional para evaluar grandes modelos de lenguaje (LLM) y agentes de IA** en razonamiento clínico y diagnóstico complejos: rendimiento diagnóstico, fiabilidad del razonamiento y sesgo relacionado con los SDoH, bajo un protocolo común.

**PRISM-Med: evaluación multidimensional de grandes modelos de lenguaje en diagnóstico médico complejo**

Este repositorio implementa el benchmark **PRISM-Med**: diagnóstico en un conjunto de casos desafiantes, fiabilidad del razonamiento y sesgo en determinantes sociales de la salud (SDoH) se combinan en una puntuación compuesta (`Benchmark_Score_100`), apta para comparar modelos y flujos agenticos en igualdad de condiciones.

### Protocolo de evaluación (ejecuciones de referencia)

La tabla pública y las puntuaciones al estilo del artículo usan un protocolo fijo de **tres repeticiones**:

1. **Tres pasadas independientes por caso** — cada modelo sujeto responde **tres veces** los mismos casos (ids de ronda `1_5answer`, `1_5answer_1`, `1_5answer_2` en `config/legacy_script_config.py`), incluidas las ramas de desafío y SDoH cuando corresponda.
2. **Clasificación diagnóstica → voto mayoritario** — tras el juicio por ronda del Top-1 y de las listas diferenciales frente a la referencia, **las etiquetas a nivel de caso se fusionan por mayoría entre las tres rondas** (etapa `classification_vote`). La precisión/cobertura del conjunto de casos difíciles y las entradas de puntuación usan esas etiquetas votadas.
3. **Clasificación de fallos de razonamiento → agregación directa** — las auditorías del contenido de razonamiento **no** se someten a voto; **las tres rondas se agregan directamente** (todas las clasificaciones de flaws de cada ronda entran en el conjunto fusionado), y las tasas de flaws severos de la parte de fiabilidad del razonamiento se calculan sobre esa vista combinada.

La reproducción local sigue los mismos valores por defecto salvo que sobrescriba las listas de rondas con variables `PRISM_*` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

**Actualizamos de forma continua** la **tabla de clasificación pública de modelos** conforme terminan nuevas evaluaciones y **publicamos progresivamente** conjuntos de datos adicionales. Siga este repositorio para figuras, tablas y lanzamientos en `dataset/`.

Todos los comandos asumen que el directorio actual es la **raíz del repositorio** (carpeta que contiene `run_prism_benchmark.py`).

## Resumen

### Clasificación de modelos (ejecución de referencia)

Clasificación ilustrativa de una evaluación PRISM-Med completada (reproducible localmente con el pipeline siguiente). **Esta tabla es una instantánea**; la actualizaremos con más modelos y ampliaremos la cobertura de datos en futuras versiones.

<p align="center">
  <img src="img/benchmark_scores.png" alt="Clasificación de puntuaciones PRISM-Med" width="900">
</p>

<p align="center"><sub>Vectorial en alta resolución: <a href="img/benchmark_scores.pdf">img/benchmark_scores.pdf</a></sub></p>

#### Modelos evaluados (ejecución de referencia)

La figura resume las puntuaciones compuestas **PRISM-Med** (`Benchmark_Score_100`) de los modelos siguientes. **Versión** son los `model_id` de API usados (véase `model_config/model_config.example.json`).

| LLM | Versión (id de modelo API) | Empresa |
|-----|----------------------------|---------|
| Claude-4-Sonnet | `claude-sonnet-4-20250514` | Anthropic |
| Claude-4.5-Sonnet | `claude-sonnet-4-5-20250929` | Anthropic |
| DeepSeek-V3.1 | `deepseek-v3-1-250821` | DeepSeek |
| DeepSeek-V3.2 | `deepseek-v3.2-thinking` | DeepSeek |
| DeepSeek-V4 Pro | `deepseek-v4-pro` | DeepSeek |
| Gemini-2.5-Flash | `gemini-2.5-flash` | Google |
| Gemini-2.5-Pro | `gemini-2.5-pro` | Google |
| Gemini-3-Pro | `gemini-3-pro-preview` | Google |
| Gemini-3.5-Flash | `gemini-3.5-flash` | Google |
| GLM-4.5 | `glm-4.5` | Zhipu AI |
| GPT-4o | `gpt-4o-2024-11-20` | OpenAI |
| GPT-5 | `gpt-5-2025-08-07` | OpenAI |
| GPT-5-Mini | `gpt-5-mini-2025-08-07` | OpenAI |
| GPT-5.1-High | `gpt-5.1-high` | OpenAI |
| GPT-5.5 | `gpt-5.5` | OpenAI |
| Grok-4.1 | `grok-4.1` | xAI |
| O3 | `o3-2025-04-16` | OpenAI |
| O3-Pro | `o3-pro-2025-06-10` | OpenAI |
| O4-mini | `o4-mini-2025-04-16` | OpenAI |

Los modelos por defecto en `config/legacy_script_config.py` pueden ser un subconjunto; use `PRISM_*_MODELS` o `--models` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

### Conjuntos de datos de evaluación

PRISM-Med utiliza dos recursos de casos vinculados (resumen en el artículo, Fig. 1):

**Challenging Case Dataset** — De 1.672 informes recopilados en *NEJM* y revistas de la *JAMA Network*, se excluyeron 730 tras cribado clínico; quedan **942** casos (oncología 269, infecciosas 159, genéticas o congénitas 140, tóxicas/farmacológicas o iatrogénicas 74, traumáticas/mecánicas 59, vasculares 39, otras 66; Fig. 2A). Modo completo: `dataset/question/query_question.xlsx` (942 filas), catálogos en `dataset/Challenge_Dataset/`.

**Simulated SDoH Dataset** — **289** casos (~30,7 %) evalúan sesgos relacionados con SDoH, con **578** escenarios contrafactuales emparejados (perfiles SDoH con menos vs más recursos): congruentes con perfil menos favorecido (89), congruentes con perfil más favorecido (88), neutros SDoH (112); Fig. 2B. Listas en `dataset/SDoH_Dataset/`; las etapas de conteo requieren localmente el árbol `bias_analysis_*` (~289 carpetas) — [docs/BENCHMARK.md](docs/BENCHMARK.md).

Copyright y citas: [dataset/README.md](dataset/README.md).

### Pipeline del benchmark

`Benchmark_Score_100` combina **rendimiento diagnóstico** en el conjunto difícil, **tasa de fallos de razonamiento severos** e **indicadores de sesgo SDoH** (p. ej. IR, SSR). Doce etapas en total; detalles y modo SDoH parcial: [docs/BENCHMARK.md](docs/BENCHMARK.md).

<p align="center">
  <img src="img/flowchart.png" alt="Diagrama del pipeline PRISM-Med" width="900">
</p>

<p align="center"><sub>Vectorial en alta resolución: <a href="img/flowchart.pdf">img/flowchart.pdf</a></sub></p>

**Licencia:** [MIT License](LICENSE) para **software y documentación** de este repositorio. El **texto clínico** en `dataset/` sigue sujeto a **derechos de autor de los editores originales** — véase [dataset/README.md](dataset/README.md). Metadatos de cita: [CITATION.cff](CITATION.cff).

## Cita

El manuscrito que describe PRISM-Med está **en revisión por pares** en *npj Digital Medicine*. El artículo completo **aún no está** en un servidor de preprints (sin DOI de preprint). Hasta la publicación en la revista, cite **este repositorio** y el título y autores siguientes; añadiremos el DOI oficial tras la aceptación.

El panel **Cite this repository** de GitHub lee [CITATION.cff](CITATION.cff).

Si utiliza este benchmark o código, cite:

> **PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis**  
> Xintian Yang¹*, Qin Su²*, Yukang Liu²*, Hui Luo², Xiangping Wang², Gui Ren², Xiaoyu Kang², Weijie Xue³, Yuemin Feng¹, Ben Wang¹, Qianqian Xu¹, Lei Shi¹, Qi Zhao¹, Shuhui Liang², Yong Lv², Yongzhan Nie², Lina Zhao⁴, Han Wang⁵‡, Yanglin Pan²‡, Hongwei Xu¹,⁶‡  
> *Contribución igual. ‡Autores de correspondencia.  
> *npj Digital Medicine* (en revisión por pares; sin preprint público).

Ejemplo BibTeX (sustituya `note` por volumen/páginas/DOI tras la publicación):

```bibtex
@article{yang2026prismmed,
  title   = {PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis},
  author  = {Yang, Xintian and Su, Qin and Liu, Yukang and Luo, Hui and Wang, Xiangping and Ren, Gui and Kang, Xiaoyu and Xue, Weijie and Feng, Yuemin and Wang, Ben and Xu, Qianqian and Shi, Lei and Zhao, Qi and Liang, Shuhui and Lv, Yong and Nie, Yongzhan and Zhao, Lina and Wang, Han and Pan, Yanglin and Xu, Hongwei},
  journal = {npj Digital Medicine},
  year    = {2026},
  note    = {Under peer review at npj Digital Medicine; no preprint. Benchmark: https://github.com/MedicalkodeFish/PRISM-Med-Benchmark-Open}
}
```

## Contenido del repositorio

| Incluido | No incluido (generado localmente) |
|----------|-----------------------------------|
| Listas y catálogos en `dataset/` (942 consultas en modo completo) | Salidas LLM en `benchmark/result/` |
| Prompts (`prompt/`), reglas de clasificación, tabla de sesgo (`benchmark/reference_table_bias_with_doi.xlsx`) | Manifiestos en `prism_benchmark/runs/` |
| Código del pipeline (`stages/`, `lib/`, `prism_benchmark/`) | Libro de puntuaciones hasta completar el pipeline |
| Plantilla API (`model_config/model_config.example.json`) | Árbol de preprocesado SDoH completo (`bias_analysis_*`, ~289 carpetas) — [docs/BENCHMARK.md](docs/BENCHMARK.md) |

**Datos clínicos:** las viñetas enlazan informes **NEJM** / **JAMA** vía **DOI**. Lea [dataset/README.md](dataset/README.md) antes de redistribuir texto de casos.

## Requisitos

- **Python 3.10+**
- Dependencias:

```powershell
pip install -r requirements.txt
```

## Inicio rápido

Comandos en **Windows PowerShell** desde la **raíz del repositorio**. En Linux/macOS use `python3`, rutas con `/` y `cp` en lugar de `Copy-Item`.

1. **Instalar dependencias** (véase [Requisitos](#requisitos)).

2. **Configurar API** — copie la plantilla y edite `model_config/model_config.json` (`api_key`, `url`; ids como en la [tabla de modelos](#modelos-evaluados-ejecución-de-referencia)).

```powershell
Copy-Item .\model_config\model_config.example.json .\model_config\model_config.json
# Edite model_config\model_config.json (no suba claves reales).
```

3. **Preflight (sin llamadas API)** — sin datos `bias_analysis_*` de la rama SDoH (~289 carpetas), puede ejecutar solo diagnóstico y razonamiento (modo SDoH parcial):

```powershell
$env:PRISM_ALLOW_PARTIAL_SDOH = "1"
python .\run_prism_benchmark.py --check-only --no-pause
```

   Código de salida `0`: los activos de datos son correctos para el modo elegido. Detalles: [docs/BENCHMARK.md](docs/BENCHMARK.md).

4. **Modelos sujetos** — valores por defecto en `config/legacy_script_config.py`. Sobrescritura (ids separados por comas):

```powershell
$env:PRISM_BASE_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_BIAS_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_CLASSIFICATION_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_SUMMARY_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_COUNT_TARGET_MODELS = "gpt-5.5,gemini-3.5-flash"
```

   Modelos juez: `model_config.json` y variables `PRISM_REASONING_LLM_MODEL`, `PRISM_COUNT_MODEL` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

5. **Puntuación compuesta completa (con SDoH, estilo artículo)** — proporcione `bias_analysis_*` externo, sin `PRISM_ALLOW_PARTIAL_SDOH`. 12 pasos, sonda API, posible coste y tiempo:

```powershell
Remove-Item Env:PRISM_ALLOW_PARTIAL_SDOH -ErrorAction SilentlyContinue
python .\run_prism_benchmark.py --no-pause
```

   **Solo diagnóstico + razonamiento:** `$env:PRISM_ALLOW_PARTIAL_SDOH = "1"` o `--allow-partial-sdoh`.

6. **Salidas** (tras ejecución correcta):

| Artefacto | Ruta |
|-----------|------|
| JSON/texto LLM por etapa | `benchmark/result/<model>/…` |
| Libro de puntuaciones | `benchmark/benchmark_scores_output.xlsx` |
| Manifiesto / tabla de finalización | `prism_benchmark/runs/` |

   Vuelva a ejecutar el mismo comando para **reanudar** casos incompletos; use `--check-only` para ver el estado de las etapas.

Más información: [docs/BENCHMARK.md](docs/BENCHMARK.md) · [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)

## Comandos habituales (Windows PowerShell)

| Objetivo | Comando |
|----------|---------|
| Comprobación de datos y activos del pipeline | `python .\run_prism_benchmark.py --check-only --no-pause` |
| Benchmark de 12 pasos | `python .\run_prism_benchmark.py --no-pause` o `run_prism_full_benchmark.bat` |
| Restaurar consultas y tablas de referencia | `python .\prism_benchmark\scripts\prepare_full_benchmark_data.py` |
| Solo pipeline | `python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json` |

Guía: [docs/BENCHMARK.md](docs/BENCHMARK.md) · Estructura: [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) · Orquestación: [prism_benchmark/README.md](prism_benchmark/README.md)

## Puntos de entrada

- `run_prism_benchmark.py` — lanzador recomendado (preflight, sonda API, 12 pasos, tabla de finalización)
- `prism_benchmark/scripts/run_pipeline.py` — pipeline por configuración
- `prism_benchmark/scripts/data_assets_check.py` — comprobación de datos y tres módulos de evaluación (independiente)
- `prism_benchmark/scripts/benchmark_verify.py` — verificación por paso (`list_missing_cases.py` lo envuelve)
