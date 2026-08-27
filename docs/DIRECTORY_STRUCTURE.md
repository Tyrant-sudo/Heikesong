# 目录结构说明

```text
Heikesong/
├─ config/test/v1.yaml             # V1 阈值、环境与安全配置
├─ docs/
│  ├─ architecture/
│  │  └─ V1_ARCHITECTURE.md        # 模块边界、数据流和扩展点
│  └─ testing/
│     ├─ V1_TEST_LIST.md           # 首批用例总表
│     ├─ V1_TEST_PLAN.md           # 范围、阶段和发布门槛
│     ├─ TRACEABILITY.md           # 需求—测试追踪矩阵
│     ├─ INCREMENTAL_TESTING.md    # 增量与回归规则
│     ├─ TEST_CASE_TEMPLATE.md     # 新场景用例模板
│     └─ forms/                    # 执行记录、CSV、批次汇总表
├─ src/heikesong/
│  ├─ core/                        # 稳定领域模型、事件和状态
│  ├─ perception/                  # 垫子、用户、姿态感知接口
│  ├─ behavior/                    # 环绕、跟随和行为编排接口
│  ├─ actions/                     # 机器狗与拍照设备接口
│  ├─ services/                    # 计时等无硬件服务
│  └─ safety/                      # 运动许可与抢占接口
├─ tests/
│  ├─ unit/                        # 纯逻辑、计时、边界测试
│  ├─ integration/                 # 模块契约与 Mock 设备测试
│  ├─ hardware/                    # 正式 SDK 与真机接口测试
│  ├─ scenarios/v1/                # V1 单项和端到端场景
│  ├─ manual/                      # 现场人工检查表
│  ├─ fixtures/                    # 测试数据说明和小型合成数据
│  └─ reports/                     # 本地生成结果，不纳入 Git
├─ tools/                          # 结构校验与测试入口
├─ function.md                     # 原始功能说明
├─ CONTRIBUTING.md                 # Git 和协作规则
└─ CHANGELOG.md                    # 版本变化
```

## 源码归属原则

### `core/`

只放跨模块稳定的数据结构和事件，不导入具体模型、相机或机器人 SDK。观察结果必须携带置信度和时间戳；姿态触发、动作与照片通过关联 ID 追踪。

### `perception/`

输入图像或录像，输出垫子、用户和姿态观察结果。具体模型可替换；行为层只依赖接口，不依赖 OpenCV、PyTorch 等实现细节。

### `behavior/`

管理垫边环绕、方向跟随、姿态响应和状态互斥。每个可能运动的行为必须支持取消，且不能绕过安全层直接控制设备。

### `actions/`

隔离机器人动作与相机拍照。普通版设备没有正式 SDK 时，用 Mock Adapter 保持上层开发可进行，禁止通过逆向或破解接入。

### `services/`

放置计时等独立业务服务。服务应使用可注入依赖，便于确定性测试。

### `safety/`

统一判断运动是否允许，并抢占环绕和跟随。安全参数未获批准时不得执行真机移动。

## 测试目录原则

- `unit/` 不访问网络、摄像头和真实硬件。
- `integration/` 验证“观察结果→行为→动作接口”和“安全事件→取消”。
- `hardware/` 只测试厂商正式支持的接口，并记录设备、固件和 SDK。
- `scenarios/v1/` 使用稳定用例 ID；自动化后保留同一编号。
- `fixtures/` 不提交可识别真人的原始视频、照片、语音或大模型文件。
- `reports/` 存本地或 CI 输出，表单模板放在 `docs/testing/forms/`。

## 增量目录规则

优先在现有模块内新增小接口；只有出现独立职责和独立生命周期时才新建顶层模块。新增 V2 场景放入 `tests/scenarios/v2/`，不得覆盖 V1 用例；跨版本共用的回归测试仍保留原始稳定 ID。
