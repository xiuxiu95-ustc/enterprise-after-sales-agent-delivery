# Enterprise Slot Extractor

企业售后预约槽位的后训练与推理组件，保留原算法工程的推理后端工厂、结构化生成、数据构建、SFT/DPO、量化、评估和本地双模型工具循环，并将领域合同统一为工程师、服务时间、时长、能力等级、问题类别和技能偏好。

主服务不复制模型调用逻辑，而是通过 `slot_extractor.inference.factory.build_backend_from_config` 创建 backend，并向 `Backend.generate` 传入企业预约 JSON Schema。未配置模型时，主服务使用确定性规则降级。

## 目录

```text
configs/        # 推理、训练、量化、工具循环配置
data/           # 轻量评估、校准和工程师排班夹具
deployment/     # 本地推理部署边界
models/         # 轻量 adapter 元数据；大权重不入库
scripts/        # 数据、训练、评估、量化入口
src/            # 可安装的 slot_extractor 包
tests/          # 原组件单元/集成合同测试
```

## 单独安装与测试

```powershell
pip install -e .
pytest
```

训练语料、运行日志、合并权重和 GGUF 属于可再生产物，不进入主仓库；具体边界见 [INTEGRATION_MANIFEST.md](INTEGRATION_MANIFEST.md)。
