# B7 · 参考文献幻觉检测

输入参考文献材料，直观看到文献分组、字段解析、检索证据与核验结果。这个仓库仅维护参考文献检测应用。

支持普通文字 PDF、DOCX、TXT、扫描件和截图。核验范围是**作品是否存在、是否对应同一作品，以及引用字段有什么差异**；不判断文献内容是否支持论文正文的某句话。

## 本地启动（Windows）

需要 Python 3.13+，在 PowerShell 中运行：

```powershell
.\setup.ps1
# 在本机 .env 填写自己的 DEEPSEEK_API_KEY
.\start.ps1
```

也可双击 `启动文献核验.cmd`。启动器默认使用 `http://127.0.0.1:8876`，端口冲突时选择空闲端口并输出实际地址；在终端按 Ctrl+C 停止服务。

文本模型用于必要的提取、疑难题名或用户启用的有限复核；常见路径优先算法处理。扫描件和截图另外需要配置 `LLM_API_KEY`、`LLM_API_BASE`、`LLM_MODEL`。OpenAlex Key 可选，Crossref 优先且证据充分后停止补查。

新克隆默认使用 GROBID、AnyStyle 公共解析及格式转换，不需要 Docker/WSL/Ruby。已有的 AnyStyle 本地格式转换加速仍可选用，见 [运行时说明](shared/README.md)。公共服务可能限流或暂不可用，系统保留失败原因并支持继续补查。

## 页面与证据

左侧显示参考文献原文和彩色字段定位，右侧显示所选引用的字段，下方显示核验比较与来源。原始响应、转换、程序执行与模型调用记录保存在本机 `data/reference`，可以导出审计包。

“已找到作品”不等于所有引用字段正确；“证据不足／待核验”也不等于文献虚构。

## 开发与构建

```powershell
.\test.ps1
```

目录：`reference-checker/` 为全部检测核心与网页，`b7_shared/` 为必要配置与限流，`release/` 为独立桌面端源码。桌面程序在应用内填写密钥，构建步骤见 [release/README.md](release/README.md)。本次迁移没有重新发布安装包。

不提交个人 `.env`、历史任务、论文材料、模型和二进制运行时、node_modules、安装包或测试残留。GitHub 克隆不包含原混合仓库中的任务数据；原目录保持不变。

[流程说明](docs/architecture.md) · [工具来源](docs/third-party.md) · [迁移记录](docs/migration-manifest.json)
