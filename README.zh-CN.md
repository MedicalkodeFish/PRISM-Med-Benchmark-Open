# PRISM-Med 基准测试

**语言：** [English](README.md) · [中文](README.zh-CN.md) · [Français](README.fr.md) · [Español](README.es.md)

**PRISM-Med 是一个面向大语言模型（LLM）与 AI 智能体（agent）的多维度综合评测基准**，聚焦复杂临床推理与诊断场景——不仅看单一准确率，而是通过多个互补维度系统评估医学 AI 在真实应用中的能力。

**PRISM-Med：面向复杂医学诊断场景的大语言模型多维度评测**

本仓库实现 **PRISM-Med** 基准：挑战性病例诊断、推理可靠性与社会健康决定因素（SDoH）偏倚等指标融合为综合得分（`Benchmark_Score_100`），便于在相同条件下对比不同模型与智能体流水线。

### 评测协议（参考运行）

公开排行榜与论文式得分采用统一的**三轮重复**规则：

1. **每例三轮独立重复** — 每个受试模型对同一批病例**重复作答三次**（轮次 id 为 `1_5answer`、`1_5answer_1`、`1_5answer_2`，见 `config/legacy_script_config.py`），挑战集与 SDoH 分支在适用时同样按三轮执行。
2. **诊断相关分类 → 多数投票** — 各轮由评判模型对照参考标准判定 Top-1 与鉴别诊断列表后，**在病例层面将三轮分类结果按多数票合并**（`classification_vote` 阶段）；挑战集诊断部分的准确率、覆盖率及相应得分输入均基于投票后的标签。
3. **推理内容分类 → 直接汇总** — 对推理缺陷的审核**不做投票**；**将三轮结果直接汇总**（各轮 flaw 分类一并纳入合并后的病例视图），推理可靠性部分的严重推理缺陷率在该汇总结果上计算。

本地复现默认遵循上述设置；可通过 `PRISM_*` 环境变量调整轮次列表，详见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

我们会**持续更新**公开的**模型排行榜**，并在后续**逐步开源更多基准数据集**。请关注本仓库以获取更新的图表、`dataset/` 发布等。

下文所有命令均假设当前工作目录为**本仓库根目录**（包含 `run_prism_benchmark.py` 的文件夹）。

## 概览

### 模型排行榜（参考运行）

下图展示一次完整 PRISM-Med 评测的示例排名（可用下文流水线本地复现）。**该排行榜为快照**——随着更多模型完成评测，我们计划刷新排名；数据集覆盖范围也将在后续版本中扩展。

<p align="center">
  <img src="img/benchmark_scores.png" alt="PRISM-Med 模型得分排行榜" width="900">
</p>

<p align="center"><sub>高清矢量图：<a href="img/benchmark_scores.pdf">img/benchmark_scores.pdf</a></sub></p>

#### 已评测模型（参考运行）

上图汇总下列受试模型的 **PRISM-Med** 综合分（`Benchmark_Score_100`）。**版本**列为本基准使用的 API `model_id`（见 `model_config/model_config.example.json`）。

| LLM | 版本（API model id） | 公司 |
|-----|----------------------|------|
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

本地默认受试模型列表见 `config/legacy_script_config.py`，可能仅为子集；可通过 `PRISM_*_MODELS` 或 `--models` 覆盖，详见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

### 测试数据集

PRISM-Med 的评测病例由两部分构成（流程见下图与论文 Fig. 1）：

**挑战性病例集（Challenging Case Dataset）**  
从 NEJM 与 JAMA Network 等期刊共收集 1,672 份病例报告，经医师团队按诊断难度筛选后排除 730 例，保留 **942** 例。病种分布较广，主要包括肿瘤学（269）、感染性疾病（159）、遗传或先天性疾病（140）、中毒/药物或医源性损害（74）、创伤或机械性病变（59）、血管疾病（39）及其他（66）（论文 Fig. 2A）。本仓库完整模式下，查询索引见 `dataset/question/query_question.xlsx`（942 行），病例目录与 DOI 见 `dataset/Challenge_Dataset/`。

**模拟 SDoH 数据集（Simulated SDoH Dataset）**  
在上述 942 例中，经多模型初筛与医师复核后纳入 **289** 例（约占 30.7%）用于评估与 SDoH 相关的偏倚风险。每例对应一对「资源较弱 / 资源较丰富」的 SDoH 反事实情景，合计 **578** 条情景。按金标准诊断与配对 SDoH 下刻板印象一致方向的关系，病例分为：与资源较弱情景一致（89）、与资源较丰富情景一致（88）、SDoH 中性（112）（论文 Fig. 2B）。列表见 `dataset/SDoH_Dataset/`；偏倚指标计数阶段另需本地 `bias_analysis_*` 预处理树（约 289 个病例目录），见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

版权与引用说明见 [dataset/README.md](dataset/README.md)。

### 基准流水线

综合分 `Benchmark_Score_100` 由三类指标合成：**挑战集诊断表现**（Top-1 / Top-5 等）、**回答中的严重推理缺陷率**，以及 **SDoH 相关偏倚指标**（如 IR、SSR 等）。流水线共 12 个阶段，各步输入输出与可选的部分 SDoH 模式见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

<p align="center">
  <img src="img/flowchart.png" alt="PRISM-Med 基准流水线示意图" width="900">
</p>

<p align="center"><sub>高清矢量图：<a href="img/flowchart.pdf">img/flowchart.pdf</a></sub></p>

**许可：** 本仓库**软件与文档**适用 [MIT License](LICENSE)。`dataset/` 中的**临床病例文本**仍受**原出版方版权**约束——见 [dataset/README.md](dataset/README.md)。可机读引用元数据：[CITATION.cff](CITATION.cff)。

## 引用

说明 PRISM-Med 的配套论文目前在 *npj Digital Medicine* **同行评议**中；论文全文**尚未**在 bioRxiv、medRxiv 等预印本平台公开（无预印本 DOI）。在期刊正式发表前，请优先引用**本仓库**，并同时注明下列论文题目与作者；接收发表后我们会在此补充正式 DOI。

GitHub 仓库页右侧 **Cite this repository** 会读取 [CITATION.cff](CITATION.cff)（含软件条目与论文 preferred citation）。

若使用本基准或代码，请引用：

> **PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis**  
> Xintian Yang¹*, Qin Su²*, Yukang Liu²*, Hui Luo², Xiangping Wang², Gui Ren², Xiaoyu Kang², Weijie Xue³, Yuemin Feng¹, Ben Wang¹, Qianqian Xu¹, Lei Shi¹, Qi Zhao¹, Shuhui Liang², Yong Lv², Yongzhan Nie², Lina Zhao⁴, Han Wang⁵‡, Yanglin Pan²‡, Hongwei Xu¹,⁶‡  
> *同等贡献。‡通讯作者。  
> *npj Digital Medicine*（同行评议中；暂无公开预印本）。

BibTeX 示例（发表后请将 `note` 换为卷期页与 DOI）：

```bibtex
@article{yang2026prismmed,
  title   = {PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis},
  author  = {Yang, Xintian and Su, Qin and Liu, Yukang and Luo, Hui and Wang, Xiangping and Ren, Gui and Kang, Xiaoyu and Xue, Weijie and Feng, Yuemin and Wang, Ben and Xu, Qianqian and Shi, Lei and Zhao, Qi and Liang, Shuhui and Lv, Yong and Nie, Yongzhan and Zhao, Lina and Wang, Han and Pan, Yanglin and Xu, Hongwei},
  journal = {npj Digital Medicine},
  year    = {2026},
  note    = {Under peer review at npj Digital Medicine; no preprint. Benchmark: https://github.com/MedicalkodeFish/PRISM-Med-Benchmark-Open}
}
```

## 仓库内容

| 包含 | 不随仓库分发（本地生成） |
|------|--------------------------|
| `dataset/` 下病例列表与目录（完整模式 942 条挑战查询） | `benchmark/result/` 下的 LLM 输出 |
| 提示词（`prompt/`）、分类规则、偏倚参考表（`benchmark/reference_table_bias_with_doi.xlsx`） | `prism_benchmark/runs/` 下的运行清单 |
| 流水线代码（`stages/`、`lib/`、`prism_benchmark/`） | 流水线完成前的综合得分工作簿 |
| API 配置模板（`model_config/model_config.example.json`） | SDoH 偏倚模块所需的完整预处理树（`bias_analysis_*`，约 289 个病例文件夹）——见 [docs/BENCHMARK.md](docs/BENCHMARK.md) |

**临床数据：** 病例 vignette 通过 **DOI** 关联已发表的 **NEJM** / **JAMA** 等病例报告。再分发或复用病例文本前请阅读 [dataset/README.md](dataset/README.md)。

## 环境要求

- **Python 3.10+**
- 依赖安装：

```powershell
pip install -r requirements.txt
```

## 快速开始

以下命令在 **Windows PowerShell** 下从**仓库根目录**执行。Linux/macOS 请使用 `python3`、正斜杠路径，并用 `cp` 替代 `Copy-Item`。

1. **安装依赖**（见上文 [环境要求](#环境要求)）。

2. **配置 API**——复制模板并编辑 `model_config/model_config.json`：为计划运行的每个模型别名设置 `api_key` 与 `url`（id 需与[已评测模型](#已评测模型参考运行)表一致，如 `gpt-5.5`、`gemini-3.5-flash`）。

```powershell
Copy-Item .\model_config\model_config.example.json .\model_config\model_config.json
# 编辑 model_config\model_config.json（勿提交真实密钥）。
```

3. **预检（不调用 API）**——若尚无 SDoH 分支的 `bias_analysis_*` 数据（约 289 个病例文件夹），可仅跑诊断与推理两部分（部分 SDoH 模式）：

```powershell
$env:PRISM_ALLOW_PARTIAL_SDOH = "1"
python .\run_prism_benchmark.py --check-only --no-pause
```

   退出码 `0` 表示当前模式下数据资产检查通过。详情：[docs/BENCHMARK.md](docs/BENCHMARK.md)。

4. **选择受试模型**——默认见 `config/legacy_script_config.py`（`DEFAULT_MODEL_LIST`）。可用环境变量覆盖（逗号分隔的**配置 id**）：

```powershell
$env:PRISM_BASE_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_BIAS_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_CLASSIFICATION_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_SUMMARY_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_COUNT_TARGET_MODELS = "gpt-5.5,gemini-3.5-flash"
```

   检查器/评判模型：在 `model_config.json` 中配置，并可设置 `PRISM_REASONING_LLM_MODEL`、`PRISM_COUNT_MODEL` 等（见 [docs/BENCHMARK.md](docs/BENCHMARK.md)）。

5. **完整综合分（含 SDoH，与论文一致）**——提供外部 `bias_analysis_*`（junction 或 `PRISM_BIAS_ANALYSIS_ROOT`），并在**未**设置 `PRISM_ALLOW_PARTIAL_SDOH` 时运行。将执行全部 12 步、探测 API，耗时长且可能产生 API 费用：

```powershell
Remove-Item Env:PRISM_ALLOW_PARTIAL_SDOH -ErrorAction SilentlyContinue
python .\run_prism_benchmark.py --no-pause
```

   **仅诊断 + 推理：** 保持 `$env:PRISM_ALLOW_PARTIAL_SDOH = "1"` 或使用 `python .\run_prism_benchmark.py --allow-partial-sdoh --no-pause`。

6. **输出**（成功运行后）：

| 产物 | 路径 |
|------|------|
| 各阶段 LLM JSON/文本 | `benchmark/result/<model>/…` |
| 综合得分工作簿 | `benchmark/benchmark_scores_output.xlsx` |
| 运行清单 / 完成表 | `prism_benchmark/runs/` |

   重复执行同一命令可**续跑**未完成病例；随时可用 `--check-only` 查看阶段完成情况。

更多说明：[docs/BENCHMARK.md](docs/BENCHMARK.md) · [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)

## 常用命令（Windows PowerShell）

| 目标 | 命令 |
|------|------|
| 数据与流水线资产检查 | `python .\run_prism_benchmark.py --check-only --no-pause`（见[快速开始](#快速开始)第 3 步） |
| 完整 12 步基准 | `python .\run_prism_benchmark.py --no-pause` 或双击 `run_prism_full_benchmark.bat` |
| 恢复完整查询与参考表 | `python .\prism_benchmark\scripts\prepare_full_benchmark_data.py` |
| 仅流水线编排 | `python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json` |

分步指南：[docs/BENCHMARK.md](docs/BENCHMARK.md) · 目录结构：[PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) · 编排层：[prism_benchmark/README.md](prism_benchmark/README.md)

## 入口脚本

- `run_prism_benchmark.py` — 推荐启动器（预检、API 探测、12 步、完成表）
- `prism_benchmark/scripts/run_pipeline.py` — 配置驱动流水线（无启动器附加功能）
- `prism_benchmark/scripts/data_assets_check.py` — 数据集与三模块资产检查（独立）
- `prism_benchmark/scripts/benchmark_verify.py` — 分步产物校验（`list_missing_cases.py` 封装此工具）
