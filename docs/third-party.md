# 工具与算法来源

- GROBID：调用公共服务返回 TEI；利用其题名、作者 given/family 等结构，不在本机训练或部署模型。
- AnyStyle：调用公共服务解析引用；保留 CSL 和分词结果。本地可选格式转换复用上游 normalizer/CSL formatter；其依赖另行安装并保留原许可证。
- CheckIfExist / References-Validation：借鉴 GB 文献类型标记作为边界的思想，未复制其宽松的缺作者通过规则。
- RefChecker：参考姓名顺序、缩写、复姓兼容的设计与测试思想，独立实现受原文约束的姓名回映。
- HalRef：参考解析、匹配与多信号分层思想。
- Hallucinator：参考姓名指纹与显式作者覆盖思想，没有复制其 AGPL 实现代码，也没有采用任意姓氏重叠即通过的规则。

源快照：CheckIfExist `2d1df3c6bcac691e665cda06dde8b92974c66a4a`；RefChecker `66d0cb59945474a1c9bd59df6e5b40c9d0c197d3`；HalRef `64903c1278914d0333c8d871c61aeafc66fb19cf`；Hallucinator `bd077600717d7a88bbd27d2939e7f0cce33c5e13`。

没有把这些研究仓库整体放入本仓库。Python、Electron、Node、Ruby 及其第三方依赖的许可证由其上游规定；构建分发时保留对应许可。项目自有代码的整体开源许可证尚未指定。
