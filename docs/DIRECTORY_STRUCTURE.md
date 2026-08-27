# 目录结构说明

```text
Heikesong/
├─ .github/
│  ├─ workflows/                 # GitHub 自动校验
│  └─ pull_request_template.md   # 合并请求检查项
├─ config/
│  └─ test/                      # 测试阈值与环境配置
├─ docs/
│  ├─ DIRECTORY_STRUCTURE.md     # 本文件
│  └─ testing/
│     ├─ V1_TEST_PLAN.md         # V1 测试计划
│     ├─ TRACEABILITY.md         # 需求—测试追踪矩阵
│     └─ TEST_CASE_TEMPLATE.md   # 新用例模板
├─ tests/
│  ├─ unit/                      # 单模块、纯逻辑、无硬件测试
│  ├─ integration/               # 模块间契约和数据流测试
│  ├─ hardware/                  # 厂商 SDK 与真机接口测试
│  ├─ scenarios/v1/              # V1 端到端场景验收
│  ├─ manual/                    # 现场人工检查表
│  ├─ fixtures/                  # 测试数据说明与小型合成数据
│  └─ reports/                   # 本地生成结果，不纳入 Git
├─ tools/                        # 测试辅助和仓库校验工具
├─ function.md                   # 原始 V1 功能清单
├─ CONTRIBUTING.md               # Git 和协作规则
└─ CHANGELOG.md                  # 版本变化
```

## 文件归属原则

### `tests/unit/`

测试单个模块，不访问网络和真实硬件。人体姿态规则、目标选择、状态迁移、超时和安全规则优先在这里验证。

### `tests/integration/`

测试模块之间的契约，例如“感知结果 → 世界状态 → 行为事件”和“安全事件 → 动作取消”。默认使用 Mock Robot Adapter。

### `tests/hardware/`

只放厂商正式支持的接口测试。每个用例必须注明设备版本、固件、SDK、物理安全措施和操作员。普通用户版若未正式开放接口，不在此目录尝试逆向接入。

### `tests/scenarios/`

存放以用户体验和验收标准为中心的端到端用例。用例不绑定具体实现语言，可先人工执行，自动化后保留相同测试编号。

### `tests/manual/`

存放场地布置、开机前检查、紧急停止和测试结束检查表。所有真机测试开始前必须完成对应清单。

### `tests/fixtures/`

存放数据说明、元数据及允许进入 Git 的小型合成样本。真实用户视频、语音、点云、模型和大体积日志不直接提交。

### `tests/reports/`

本地或 CI 生成的结果目录，包括 JUnit、覆盖率、截图和现场记录。目录被 Git 忽略，只保留占位文件。

### `config/test/`

统一管理测试超时、置信度、重复次数和安全阈值。涉及人身安全的值在厂商确认前必须保持 `null`，不得凭经验直接用于真机。
