# 可选的本地格式转换运行时

GROBID 和 AnyStyle 的文献字段解析使用公共在线服务，不要求 Docker、Linux 或本地 CRF 模型。

新克隆的源码默认 `ANYSTYLE_FORMAT_MODE=remote`：AnyStyle 的字段格式转换也由公共服务完成，因此 Python 环境准备好即可使用。此方式会比本地转换多网络请求，受公共服务可用性约束。

本地转换加速仍保留在 `ref_app/format_anystyle.rb`、`format_locale.cjs` 和 `anystyle_formatter.py`。它不使用 LLM，也不加载 CRF 解析模型。启用它需要：

- `runtime/anystyle/rubyinstaller-3.3.12-2-x64/`：Ruby 运行时。
- `runtime/anystyle/` 下固定版本的上游 gems，以及 `node_modules/cld3-asm`。
- 源码运行时的 `runtime/node/node.exe`；桌面包复用 Electron 的 Node。

版本、下载来源和可取得的校验值见 `anystyle-runtime-lock.json`。恢复已有同版本运行时到上述目录，或通过环境变量 `B7_ANYSTYLE_HOME`、`B7_NODE_EXE` 指定位置，再设 `ANYSTYLE_FORMAT_MODE=local`。运行时和训练模型不进入 Git。

构建桌面程序时，有本地运行时则打包本地转换；没有则使用公共转换。第三方运行时若进入分发包，需一并保留其原始许可证。
