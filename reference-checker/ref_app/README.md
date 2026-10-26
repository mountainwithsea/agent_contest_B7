> 已迁入 B7 统一工作台：请从仓库根目录运行 `start.ps1`，配置使用根 `.env`。下文保留原项目说明，旧启动脚本和数据路径以根 README 为准。

# 本地文献核验应用

统一入口：上传 → 文献提取与排除复核 → 文本字段解析 → 多来源候选检索 → 作品身份及缺口补查 → 可审计报告。

```powershell
.\run-reference-app.ps1
# 本机使用198.18.0.0/15代理DNS时：
.\run-reference-app.ps1 -FakeDns
```

打开 http://127.0.0.1:8766 。服务只监听本机。当前是单用户本地应用，不是公开互联网多用户服务。无需Node构建；Python依赖沿用 requirements-reference-extraction.txt。

## 配置与范围

服务端读取仓库 `.env`，文本使用 DEEPSEEK_API_KEY、可选 DEEPSEEK_BASE_URL / DEEPSEEK_TEXT_MODEL；视觉使用 LLM_API_KEY、LLM_API_BASE、LLM_MODEL。配置不发送到浏览器。普通文字材料只用文本模型；图片和纯扫描PDF用视觉转写，再以文本处理，避免重复视觉分组。

支持 PDF、普通 DOCX、UTF-8 TXT、PNG/JPEG。每任务20MB，引用数量不设50条硬上限，按条解析、检索、核验并保存断点；PDF不设总页数上限、选定参考页最多8页；视觉转写最多8页，每调用最多两次格式尝试。混合PDF与含图片／修订的复杂Word明确报错。用户提供完整材料，系统不判断外部是否漏传。

不评估论文正文论断是否得到引用支持。作品身份、字段／版本问题、程序执行分别展示；流程完成不是所有引用通过。

检索适配器从原研究脚本迁移为无固定样本输入的模块，默认 Crossref、DataCite、arXiv、Europe PMC、OpenAlex、DeepSeek Search；图书另查 Open Library 与 Google Books。失败状态和空候选保留。身份阶段复用 reference_identity 的有预算补查；网络失败不能作为不存在证据。

## 进度与续跑

- 实时页面每1.5秒读取持久化事件；显示真实API步骤、已完成阶段数和条目数，不估算耗时百分比。
- 每任务独立worker，单例服务、任务文件锁、PID与创建时间共同防止重复处理。服务意外停止后可重新连接仍在运行的worker并取消。
- 用户取消终止该任务worker；已发出的远端请求可能已计费。刷新页面不取消任务。
- 续跑核验输入、代码、模型配置一致；完整checkpoint复用，损坏JSON视作未完成。未完成尝试用新目录，保留旧响应和模型日志；代码改变需新建任务。
- 完成单条结果立即出现。提取不确定性显示为输入警示，最终结果只覆盖提取到的引用。

## 审计

任务位于 `output/reference-app/<job-id>/`：输入快照、manifest代码及输入哈希、code源码快照、events.jsonl事件、每阶段JSON、模型prompt/answer、原始HTTP响应、identity报告、inventory文件哈希索引。网页提供单文件访问与ZIP导出。

ZIP包含原输入与检索材料；不包含.env。文本模型日志可能包含上传内容。失败／取消的导出是当时快照，可能没有最终inventory。实验测试记录在 experiments/web_app/2026-10-22。

安全边界：本机Host检查、同源POST与自定义请求头、文件扩展名／体积限制、路径约束、服务端密钥、引用证据URL公网检查。文件锁及PID校验避免误杀其他任务。公开部署需要额外认证、隔离和资源控制，本版没有做公开部署。
# 当前默认：工具优先完整核验

运行仓库根目录 `run-reference-app.ps1`，打开 `http://127.0.0.1:8766`。当前机器代理网络需要时使用 `-FakeDns`（仅在明确使用 198.18.0.0/15 代理解析的环境启用）。

默认上传后完成：读取分条 → 公共 GROBID / AnyStyle → 普通接口分层查询 → 作品与字段分别判断 → 报告。查询不使用 DeepSeek Search，核验模型默认关闭；可勾选必要兜底，最多5条疑难引用、每条最多2次尝试。提取/字段解析困难项仍可能使用模型。

逐条可看原文、字段、请求、候选和字段差异；失败与未找到分开。完整报告和 ZIP 保留证据。实现和真实验收见 `docs/design/registry-first-app.md`。
