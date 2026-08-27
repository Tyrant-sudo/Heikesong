# 测试目录

测试按依赖程度从低到高组织：

1. `unit/`：纯逻辑和边界测试。
2. `integration/`：模块契约与 Mock 设备测试。
3. `hardware/`：正式 SDK 和真机接口测试。
4. `scenarios/`：端到端用户场景验收。
5. `manual/`：真机前后人工检查表。
6. `fixtures/`：测试数据说明与小型合成样本。
7. `reports/`：生成的测试结果。

新增测试前，先在 `docs/testing/TRACEABILITY.md` 中分配需求编号，再按 `docs/testing/INCREMENTAL_TESTING.md` 确定回归范围。执行结果使用 `docs/testing/forms/` 中的表单，生成物放入被忽略的 `tests/reports/`。
