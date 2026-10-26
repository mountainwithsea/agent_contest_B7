# 独立桌面端源码

这个目录仅包含文献核验的 Electron 窗口、加密设置、本机服务管理和构建脚本。应用 ID 为 `cn.edu.zzu.b7.reference`，用户数据目录为 `%APPDATA%/B7ReferenceChecker`，与旧混合工作台隔离。

在 Windows 安装 Node.js 后，先在项目根目录运行 `setup.ps1`，再执行：

```powershell
cd release
npm ci
.\build.ps1
```

构建脚本下载固定版本的嵌入式 Python，打包锁定的 Python 依赖，并生成 `artifacts/B7-Reference-Setup-版本-x64.exe` 和免安装 ZIP。安装包、运行时、构建缓存及 node_modules 均被 Git 排除。

AnyStyle 本地格式转换运行时可选，见 `../shared/README.md`。缺少该运行时的包使用公共格式转换。桌面设置仍允许用户配置自己的文本、视觉和 OpenAlex 密钥；开发者 `.env` 不会打入包内。

本次拆分只迁移和验证源码，未重新构建独立版安装包。桌面版本号 0.1.3 表示独立入口，不代表已经发布二进制文件。
