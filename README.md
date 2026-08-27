# Heikesong

面向瑜伽空间的互动机器狗项目。当前仓库处于 V1 测试基线阶段：先固定需求编号、测试分层、场景验收和安全门槛，再逐步接入感知算法与机器狗控制接口。

## 当前内容

- `function.md`：V1 原始功能清单与验收方向。
- `docs/DIRECTORY_STRUCTURE.md`：目录职责、文件归属和扩展约定。
- `docs/testing/V1_TEST_PLAN.md`：第一版测试计划和发布门槛。
- `docs/testing/TRACEABILITY.md`：需求到测试的追踪矩阵。
- `tests/`：单元、集成、真机、场景、数据和报告目录。
- `tools/validate_test_structure.py`：不依赖第三方包的仓库基线校验。

## 快速校验

```bash
python tools/validate_test_structure.py
```

该命令只检查测试基线是否完整，不会连接或控制机器狗。

## V1 测试策略

1. 使用录像和 Mock 设备先验证人体感知、行为条件和状态迁移。
2. 厂商提供受支持的 SDK 后，再执行运动、相机和安全接口的真机测试。
3. 最后在封闭瑜伽测试区完成主链和 Safety Override 验收。

真机测试必须遵循厂商安全要求。普通用户版若没有正式开放控制接口，不进行破解、逆向或绕过安全机制。
