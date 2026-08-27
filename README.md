# Heikesong

面向瑜伽空间的互动机器狗项目。V1 聚焦六项能力：识别瑜伽垫、垫边环绕、用户定位、下犬式识别后模仿并拍照、跟随用户方向、计时。代码采用可替换接口，允许先用录像和 Mock 完成验证，再接入厂商正式 SDK。

目标真机已确定为 **Vbot 超能机器狗“大头 EDU 版”**。项目版本 `0.3.0` 新增独立设备配置和 HIL 门禁；具体固件、SDK、ROS 2 发行版与接口名称必须从交付设备读取后填写，不能用公开参数代替实测。

## 当前内容

- `function.md`：原始功能清单与当前 V1 范围说明。
- `src/heikesong/`：领域契约、感知/行为/动作接口及计时服务。
- `config/device/vbot_edu.yaml`：Vbot EDU 的已确认属性与待实机发现字段。
- `docs/devices/VBOT_EDU_BASELINE.md`：设备确认结论、证据和项目影响。
- `docs/architecture/V1_ARCHITECTURE.md`：V1 模块边界与数据流。
- `docs/DIRECTORY_STRUCTURE.md`：目录职责、文件归属和扩展约定。
- `docs/testing/V1_TEST_LIST.md`：首批测试列表和执行顺序。
- `docs/testing/V1_TEST_PLAN.md`：第一版测试计划和发布门槛。
- `docs/testing/VBOT_EDU_TEST_PLAN.md`：Vbot EDU 硬件测试版本、执行顺序和放行条件。
- `docs/testing/TRACEABILITY.md`：需求到测试的追踪矩阵。
- `docs/testing/forms/`：可填写的单次记录、CSV 和批次汇总表。
- `tests/`：单元、集成、真机、场景、数据和报告目录。
- `tests/hardware/vbot_edu/`：Vbot EDU 的 8 个硬件属性与 HIL 门禁用例。
- `tools/validate_test_structure.py`：不依赖第三方包的仓库基线校验。

## 快速校验

需要 Python 3.10 或更高版本，不依赖第三方运行库。

```bash
python tools/validate_test_structure.py
python tools/run_unit_tests.py
```

该命令只检查测试基线是否完整，不会连接或控制机器狗。

## V1 测试策略

1. 使用录像校准瑜伽垫、用户位置/方向和下犬式识别。
2. 使用 Mock 设备验证环绕、跟随、姿态触发去重、计时和安全抢占。
3. 按 `VBOT_EDU_TEST_PLAN.md` 先完成设备身份、接口枚举和安全停止，再执行运动与拍照测试。
4. 最后在封闭瑜伽测试区完成完整主链验收。

真机测试必须遵循厂商安全要求。普通用户版若没有正式开放控制接口，不进行破解、逆向或绕过安全机制。
