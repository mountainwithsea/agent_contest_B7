# 作品身份自动核验

本模块从已有自动检索结果开始，读取原引用、Qwen 字段、候选及保存的原始页面，自行补查，再生成带逐字证据片段的结果。它不读取上一轮 `reference_identity_audit` 的审计答案，不按论文编号或题名写特例。

在仓库根目录运行：

```powershell
python -m reference_identity --source experiments/reference_retrieval/2026-10-21 --output experiments/reference_identity/2026-10-22/my-run --workers 4
```

文本配置使用根目录 `.env` 的 `DEEPSEEK_API_KEY`，可选 `DEEPSEEK_BASE_URL`（默认 https://api.deepseek.com）和 `DEEPSEEK_TEXT_MODEL`（默认 deepseek-flash），采用非思考模式和 JSON 输出。图像配置使用 `LLM_MODEL`、`LLM_API_BASE`、`LLM_API_KEY`；本轮图像调用预算为 0。密钥和鉴权头不写入日志。新代码或输入应使用新输出目录；完全相同的输入和代码可续跑已完成条目。

本机公网域名实际解析到代理的 `198.18.0.0/15` 虚拟 DNS 地址段，因此此次运行另加 `--fake-dns-network 198.18.0.0/15`。普通网络不需要此参数。它只允许域名解析到该代理段，仍拒绝私网、localhost、特殊 IP 字面值以及携密钥的跨源重定向。

## 自动过程

1. 从原始请求对应的候选中选择相关记录，恢复 Crossref 页码等字段，读已保存的正文；验证页明确排除。
2. 强制查原引用 arXiv 编号，并核对最多三个高相关 DOI 的登记记录。Crossref 没有对应记录时尝试 DataCite。
3. DeepSeek 读取实际证据，最多规划两轮、每轮两个行动：搜索、抓网页／PDF、查 DOI、arXiv、PMC 全文或图书版本目录。
4. 程序执行行动，单条最多 12 个请求。仅抓取证据中发现的 URL，保留成功／失败原响应和哈希。请求失败不能作为不存在证据。
5. DeepSeek 生成逐字段结论，再由单独一次模型复核检查没有依据的解释。模型不自行联网，实际查询均由上述工具执行。
6. 程序检查字段结构、证据 ID 和逐字片段；确认身份还必须有同一来源的题名和作者锚点，显式编号矛盾不能无条件通过。无法通过则保留待核。

## 状态含义

- `confirmed`：当前证据支持同一作品；字段或具体版本仍可能待核。
- `probable`：较强线索，但尚缺关键核实。
- `uncertain`：证据不足、无法解释或模型校验失败。
- `conflict`：原引用关键身份／显式标识符冲突。
- `not_found`：本轮未找到，不表示世界上不存在。

当前 schema_version=2 使用同一来源的题名与全部明确作者一对一匹配；支持有约束的姓名缩写、顺序和断词规范化。相似题名必须有同证据的已复核题名解释，分卷／数字／否定词差异不能靠相似度通过。已复核的题名或作者冲突阻止确认。旧版本的80%门槛仅保留在历史实现与旧测试中，不再作为新运行的确认规则。模型仍可能误读来源，逐字引文检查只能证明文本出现，不能完整证明语义正确；复核阶段降低但不能消除此风险。

## 产物与复现

- `index.html`：双击本地打开，不需服务端。
- `manifest.json`：输入、原始材料和代码哈希，模型配置（无密钥）及预算。
- `code/`：本次代码快照。
- `references/<id>/input.json`：原引用与解析输入。
- `evidence.json`：正文／书目／搜索线索、原始文件及哈希。
- `requests/`：每个补查请求的日志和原响应。
- `model/`：规划、判断、复核的提示词与回答，含失败重试。
- `timeline.json`：模型提出的行动及程序执行结果。
- `result.json`：程序实际最终输出；不会手工修改单条结论。

测试：`python -m unittest discover -s tests -p test_reference_identity.py`。

本阶段不是从上传文件重新开始的全流程运行。输入复用了先前自动检索材料；旧材料与本轮补查在证据中明确区分。未测试最终 NeurIPS 材料，确认比例不能当作准确率。

## 本轮运行

```powershell
python -m reference_identity --source experiments/reference_retrieval/2026-10-21 --output experiments/reference_identity/2026-10-22/run-04-deepseek --workers 4 --fake-dns-network 198.18.0.0/15 --reuse-auto-run experiments/reference_identity/2026-10-22/run-03-deepseek
```

`--reuse-auto-run` 只接受同一自动检索输入的先前自动运行。HTTP 成功响应按 URL、方法、请求体匹配并校验哈希，复制后记录复用来源；失败请求重新发送。模型响应仅在模型、地址、提示词一致时复用，因此本轮不复用 Qwen 判断。run-01、run-02 是中断的调试运行，不是交付结果。

配置隔离测试：`python -m unittest discover -s tests -p test_identity_model_client.py`。

最终交付：run-04-deepseek。45 条完成：39 条已确认作品、2 条较强线索、4 条待核（其中 B19 的复核输出未通过校验）。全程图像调用 0。最终运行新发出49次HTTP请求、复用98次原响应；新发出26次文本模型请求、复用117次同模型同提示词响应。前置run-03有150次文本请求，不能将最终运行的调用量视为整个开发过程的累计费用。

26项测试通过；核查962个证据文件哈希、500处引文、1394个本地链接；桌面及390像素手机宽度的本地网页交互验证通过。确认比例不是准确率；所有条目仍可能有字段级缺口。


## 三维结果与身份缺口补查（schema_version=2）

- `dimensions.existence`：是否有对应作品的证据（confirmed / candidate / unknown）；没有明确的不存在结论。
- `dimensions.fields`：模型逐字段比较、未解决差异，以及是否完成复核。原引用未给字段会显示unknown，不据此否定作品存在。
- `dimensions.execution`：模型阶段是否失败、是否重试恢复。有效初稿和书目证据不会因复核JSON失败被清空。
- 初始规划后作判断与独立身份检查；身份有缺口则最多再进行两轮补查。规划器没有行动时，通用策略尝试已观察到的PMC全文／作品URL／题名作者搜索。总请求上限仍为12。
- 新闻等自由文本页面需要已复核且同页的题名与署名证据；搜索摘要不能单独确认。不存在人工指定来源或逐条裁决。

五条回归命令（用户指定 B19 + A16/A17/A19/B02）：

```powershell
python -m reference_identity --source experiments/reference_retrieval/2026-10-21 --output experiments/reference_identity/2026-10-22/run-06-dimensions --ids B19 A16 A17 A19 B02 --workers 3 --fake-dns-network 198.18.0.0/15 --reuse-auto-run experiments/reference_identity/2026-10-22/run-05-dimensions
```

run-05 是三维机制初次运行；run-06 使用额外题名/姓名误确认防护，复用相同提示和成功HTTP响应。旧45条结果保持原样。本轮只复测5条，不推断其余40条均通过新流程。所有测试：`python -m unittest discover -s tests -p "*identity*.py"`。

run-06 实测5条：A16、A19、B02、B19作品身份confirmed；A17 candidate，第二轮恢复规划格式校验失败后由通用fallback继续抓取，作者署名仍只在搜索摘要，因此execution=partial且保留待核。核查94证据哈希、52引文、140本地链接及桌面/手机网页交互通过。
