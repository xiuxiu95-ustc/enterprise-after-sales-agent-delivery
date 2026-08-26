# Integration Manifest

来源组件已按企业售后领域完成以下适配：

- 人员合同统一为 `Engineer`，筛选条件统一为 `engineer_level_preference` 与技能偏好。
- 结构化输出、prompt、工具 schema、工具循环、评估断言和测试夹具同步更新。
- `find_engineers` 使用排班、能力等级和问题类别/技能匹配，不再保留旧领域筛选逻辑。
- 主系统的 `ENTERPRISE_SLOT_SCHEMA` 仍是在线业务真相；本组件只负责结构化推理，不直接写预约数据库。

版本库保留源码、配置、测试、按组件 `.gitignore` 明确版本化的训练/评估/校准数据、实验计划、报告和 adapter 元数据。下载的基础模型、真实大权重、合并模型、GGUF、训练 checkpoint、缓存和运行日志必须从受控数据/模型存储恢复，不提交到 GitHub。
