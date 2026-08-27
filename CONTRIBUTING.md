# 协作与版本管理

## 分支约定

- `main`：始终保持可验证的稳定基线。
- `feat/<name>`：产品能力开发。
- `test/<name>`：测试、数据或验收用例开发。
- `fix/<name>`：缺陷修复。
- `docs/<name>`：纯文档修改。

每个分支只处理一个主题，合并前应同步最新 `main` 并执行基线校验。

## 提交信息

采用 Conventional Commits 风格：

```text
feat(perception): add person-presence detector
test(safety): add connection-loss interruption case
docs(test-plan): clarify V1 exit criteria
fix(behavior): cancel follow action on timeout
```

## 合并要求

- 说明关联的需求编号和测试编号。
- 运行 `python tools/validate_test_structure.py`。
- 行为变化必须补充或更新测试。
- 真机测试必须附带设备型号、固件版本、接口版本和结果摘要。
- 安全相关修改至少需要一名非作者复核。

## 测试数据

- 不提交包含可识别人脸、声音或个人信息的原始数据。
- 不提交大体积视频、模型、ROS bag、点云和运行日志。
- 测试数据应记录来源、授权、采集条件、匿名化方式和校验摘要。
- 可公开的小型合成数据后续可放在 `tests/fixtures/generated/`；大文件使用受控对象存储或 Git LFS。

## 版本标记

- 测试基线使用 `v0.x.y`。
- 首个通过全部 V1 发布门槛的版本标记为 `v1.0.0`。
- 每次发布同步更新 `CHANGELOG.md`。
