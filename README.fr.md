# Benchmark PRISM-Med

**Langues :** [English](README.md) · [中文](README.zh-CN.md) · [Français](README.fr.md) · [Español](README.es.md)

**PRISM-Med est un benchmark multidimensionnel pour l’évaluation des grands modèles de langage (LLM) et des agents d’IA** en raisonnement clinique et diagnostic complexes — performance diagnostique, fiabilité du raisonnement et biais liés aux SDoH, sous un protocole commun.

**PRISM-Med : évaluation multidimensionnelle des grands modèles de langage pour le diagnostic médical complexe**

Ce dépôt implémente le benchmark **PRISM-Med** : diagnostics sur un jeu de cas difficiles, fiabilité du raisonnement et biais liés aux déterminants sociaux de la santé (SDoH) sont agrégés en un score composite (`Benchmark_Score_100`), pour comparer modèles et pipelines agentiques à périmètre égal.

### Protocole d’évaluation (exécutions de référence)

Le classement public et les scores « article » suivent un protocole fixe en **trois répétitions** :

1. **Trois passages indépendants par cas** — chaque modèle sujet répond **trois fois** aux mêmes cas (identifiants de tour `1_5answer`, `1_5answer_1`, `1_5answer_2` dans `config/legacy_script_config.py`), y compris les branches jeu de défi et SDoH le cas échéant.
2. **Classification diagnostique → vote majoritaire** — après jugement par tour du Top-1 et des diagnostics différentiels par rapport à la référence, **les étiquettes au niveau cas sont fusionnées par vote majoritaire sur les trois tours** (étape `classification_vote`). Précision/couverture sur le jeu de cas difficiles et entrées de score associées reposent sur ces étiquettes votées.
3. **Classification des défauts de raisonnement → agrégation directe** — les audits du contenu de raisonnement **ne** sont **pas** soumis au vote ; **les trois tours sont agrégés directement** (toutes les classifications de flaws de chaque tour contribuent à l’ensemble fusionné), et les taux de flaws sévères de la partie « fiabilité du raisonnement » sont calculés sur cette vue combinée.

La reproduction locale utilise les mêmes valeurs par défaut, sauf surcharge des listes de tours via les variables `PRISM_*` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

Nous **mettons à jour en continu** le **classement public des modèles** au fil des évaluations et **publions progressivement** des jeux de données supplémentaires. Surveillez ce dépôt pour les figures, tableaux et versions `dataset/` actualisés.

Toutes les commandes ci-dessous supposent que le répertoire courant est la **racine du dépôt** (dossier contenant `run_prism_benchmark.py`).

## Vue d’ensemble

### Classement des modèles (exécution de référence)

Classement illustratif issu d’une évaluation PRISM-Med complète (reproductible localement avec le pipeline ci-dessous). **Ce classement est un instantané** — nous prévoyons de le rafraîchir à mesure que d’autres modèles sont évalués ; la couverture des données évoluera aussi.

<p align="center">
  <img src="img/benchmark_scores.png" alt="Classement des scores PRISM-Med" width="900">
</p>

<p align="center"><sub>Vectoriel haute résolution : <a href="img/benchmark_scores.pdf">img/benchmark_scores.pdf</a></sub></p>

#### Modèles évalués (exécution de référence)

La figure résume les scores composites **PRISM-Med** (`Benchmark_Score_100`) pour les modèles ci-dessous. La colonne **Version** indique les `model_id` API utilisés (voir `model_config/model_config.example.json`).

| LLM | Version (id modèle API) | Société |
|-----|-------------------------|---------|
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

Les modèles par défaut dans `config/legacy_script_config.py` peuvent n’en lister qu’un sous-ensemble ; surchargez via `PRISM_*_MODELS` ou `--models` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

### Jeux de données d’évaluation

PRISM-Med repose sur deux ressources de cas liées (aperçu : article, Fig. 1) :

**Challenging Case Dataset** — Sur 1 672 rapports de cas recueillis dans *NEJM* et les revues du *JAMA Network*, 730 cas ont été exclus après criblage par des cliniciens ; **942** cas restent (oncologie 269, maladies infectieuses 159, troubles génétiques ou congénitaux 140, toxiques/médicamenteux ou iatrogènes 74, traumatiques/mécaniques 59, vasculaires 39, autres 66 ; Fig. 2A). En mode complet : `dataset/question/query_question.xlsx` (942 lignes), catalogues sous `dataset/Challenge_Dataset/`.

**Simulated SDoH Dataset** — **289** cas (~30,7 %) servent à évaluer les biais liés aux SDoH, avec **578** scénarios contre-factuels appariés (profils SDoH moins vs plus favorisés) : congruents profil moins favorisé (89), congruents profil plus favorisé (88), neutres SDoH (112) ; Fig. 2B. Listes : `dataset/SDoH_Dataset/` ; les étapes de comptage exigent en local l’arborescence `bias_analysis_*` (~289 dossiers) — [docs/BENCHMARK.md](docs/BENCHMARK.md).

Droits d’auteur et citations : [dataset/README.md](dataset/README.md).

### Pipeline du benchmark

Le score `Benchmark_Score_100` combine **performance diagnostique** sur le jeu difficile, **taux de flaws de raisonnement sévères** et **indicateurs de biais SDoH** (p. ex. IR, SSR). Douze étapes au total ; détails et mode SDoH partiel : [docs/BENCHMARK.md](docs/BENCHMARK.md).

<p align="center">
  <img src="img/flowchart.png" alt="Schéma du pipeline PRISM-Med" width="900">
</p>

<p align="center"><sub>Vectoriel haute résolution : <a href="img/flowchart.pdf">img/flowchart.pdf</a></sub></p>

**Licence :** [MIT License](LICENSE) pour le **logiciel et la documentation** de ce dépôt. Le **texte clinique** dans `dataset/` reste soumis aux **droits des éditeurs d’origine** — voir [dataset/README.md](dataset/README.md). Métadonnées de citation : [CITATION.cff](CITATION.cff).

## Citation

Le manuscrit décrivant PRISM-Med est **en cours d’évaluation par les pairs** dans *npj Digital Medicine*. Le texte intégral **n’est pas encore** déposé sur un serveur de preprints (pas de DOI de preprint). En attendant la publication, citez **ce dépôt** ainsi que le titre et les auteurs ci-dessous ; nous ajouterons le DOI officiel après acceptation.

Le panneau **Cite this repository** sur GitHub lit [CITATION.cff](CITATION.cff).

Si vous utilisez ce benchmark ou ce code, veuillez citer :

> **PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis**  
> Xintian Yang¹*, Qin Su²*, Yukang Liu²*, Hui Luo², Xiangping Wang², Gui Ren², Xiaoyu Kang², Weijie Xue³, Yuemin Feng¹, Ben Wang¹, Qianqian Xu¹, Lei Shi¹, Qi Zhao¹, Shuhui Liang², Yong Lv², Yongzhan Nie², Lina Zhao⁴, Han Wang⁵‡, Yanglin Pan²‡, Hongwei Xu¹,⁶‡  
> *Contribution égale. ‡Auteurs correspondants.  
> *npj Digital Medicine* (en évaluation par les pairs ; pas de preprint public).

Exemple BibTeX (remplacez `note` par volume/pages/DOI après publication) :

```bibtex
@article{yang2026prismmed,
  title   = {PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis},
  author  = {Yang, Xintian and Su, Qin and Liu, Yukang and Luo, Hui and Wang, Xiangping and Ren, Gui and Kang, Xiaoyu and Xue, Weijie and Feng, Yuemin and Wang, Ben and Xu, Qianqian and Shi, Lei and Zhao, Qi and Liang, Shuhui and Lv, Yong and Nie, Yongzhan and Zhao, Lina and Wang, Han and Pan, Yanglin and Xu, Hongwei},
  journal = {npj Digital Medicine},
  year    = {2026},
  note    = {Under peer review at npj Digital Medicine; no preprint. Benchmark: https://github.com/MedicalkodeFish/PRISM-Med-Benchmark-Open}
}
```

## Contenu du dépôt

| Inclus | Non fourni (généré localement) |
|--------|--------------------------------|
| Listes et catalogues sous `dataset/` (942 requêtes en mode complet) | Sorties LLM sous `benchmark/result/` |
| Prompts (`prompt/`), règles de classification, table de biais (`benchmark/reference_table_bias_with_doi.xlsx`) | Manifestes sous `prism_benchmark/runs/` |
| Code du pipeline (`stages/`, `lib/`, `prism_benchmark/`) | Classeur de scores jusqu’à la fin du pipeline |
| Modèle de config API (`model_config/model_config.example.json`) | Arborescence de prétraitement SDoH complète (`bias_analysis_*`, ~289 dossiers) — [docs/BENCHMARK.md](docs/BENCHMARK.md) |

**Données cliniques :** les vignettes renvoient aux cas **NEJM** / **JAMA** via **DOI**. Lisez [dataset/README.md](dataset/README.md) avant toute redistribution.

## Prérequis

- **Python 3.10+**
- Dépendances :

```powershell
pip install -r requirements.txt
```

## Démarrage rapide

Commandes en **Windows PowerShell** depuis la **racine du dépôt**. Sous Linux/macOS : `python3`, chemins avec `/`, `cp` au lieu de `Copy-Item`.

1. **Installer les dépendances** (voir [Prérequis](#prérequis)).

2. **Configurer l’API** — copiez le modèle et éditez `model_config/model_config.json` (`api_key`, `url` ; ids comme dans le [tableau des modèles](#modèles-évalués-exécution-de-référence)).

```powershell
Copy-Item .\model_config\model_config.example.json .\model_config\model_config.json
# Éditez model_config\model_config.json (ne commitez pas les clés).
```

3. **Prévol (sans appels API)** — sans `bias_analysis_*` pour la branche SDoH (~289 dossiers), vous pouvez n’exécuter que diagnostic + raisonnement (mode SDoH partiel) :

```powershell
$env:PRISM_ALLOW_PARTIAL_SDOH = "1"
python .\run_prism_benchmark.py --check-only --no-pause
```

   Code de sortie `0` : les actifs de données sont OK pour le mode choisi. Détails : [docs/BENCHMARK.md](docs/BENCHMARK.md).

4. **Modèles sujets** — défauts dans `config/legacy_script_config.py`. Surcharge (ids séparés par des virgules) :

```powershell
$env:PRISM_BASE_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_BIAS_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_CLASSIFICATION_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_SUMMARY_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_COUNT_TARGET_MODELS = "gpt-5.5,gemini-3.5-flash"
```

   Modèles juge : `model_config.json` et variables `PRISM_REASONING_LLM_MODEL`, `PRISM_COUNT_MODEL` ([docs/BENCHMARK.md](docs/BENCHMARK.md)).

5. **Score composite complet (avec SDoH, style article)** — fournissez `bias_analysis_*` externe, sans `PRISM_ALLOW_PARTIAL_SDOH`. 12 étapes, sonde API, coût/temps possibles :

```powershell
Remove-Item Env:PRISM_ALLOW_PARTIAL_SDOH -ErrorAction SilentlyContinue
python .\run_prism_benchmark.py --no-pause
```

   **Diagnostic + raisonnement seulement :** `$env:PRISM_ALLOW_PARTIAL_SDOH = "1"` ou `--allow-partial-sdoh`.

6. **Sorties** (après succès) :

| Artefact | Chemin |
|----------|--------|
| JSON/texte LLM par étape | `benchmark/result/<model>/…` |
| Classeur de scores | `benchmark/benchmark_scores_output.xlsx` |
| Manifeste / tableau de complétion | `prism_benchmark/runs/` |

   Relancez la même commande pour **reprendre** les cas incomplets ; `--check-only` pour l’état des étapes.

Plus d’infos : [docs/BENCHMARK.md](docs/BENCHMARK.md) · [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)

## Commandes courantes (Windows PowerShell)

| Objectif | Commande |
|----------|----------|
| Vérification des données et des actifs du pipeline | `python .\run_prism_benchmark.py --check-only --no-pause` |
| Benchmark 12 étapes | `python .\run_prism_benchmark.py --no-pause` ou `run_prism_full_benchmark.bat` |
| Restaurer requêtes et tables de référence | `python .\prism_benchmark\scripts\prepare_full_benchmark_data.py` |
| Pipeline seul | `python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json` |

Guide : [docs/BENCHMARK.md](docs/BENCHMARK.md) · Arborescence : [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) · Couche d’orchestration : [prism_benchmark/README.md](prism_benchmark/README.md)

## Points d’entrée

- `run_prism_benchmark.py` — lanceur recommandé (prévol, sonde API, 12 étapes, tableau de complétion)
- `prism_benchmark/scripts/run_pipeline.py` — pipeline piloté par config
- `prism_benchmark/scripts/data_assets_check.py` — vérification des jeux de données et des trois modules d’évaluation (autonome)
- `prism_benchmark/scripts/benchmark_verify.py` — vérification par étape (`list_missing_cases.py` l’enveloppe)
