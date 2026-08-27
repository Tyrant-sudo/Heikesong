# 场景测试

场景用例描述用户可观察的完整行为，不绑定具体实现。

命名规则：

```text
TC-<领域>-<三位编号>-<简短名称>.md
```

V1 领域：`MAT`、`PER`、`POSE`、`BEH`、`ACT`、`TIM`、`SAFE`、`E2E`。

场景文件描述用户可观察结果；阈值引用 `config/test/v1.yaml`，不要在多个用例里复制数值。执行结果不回写场景文件，统一填写 `docs/testing/forms/V1_TEST_RECORD.md`。
