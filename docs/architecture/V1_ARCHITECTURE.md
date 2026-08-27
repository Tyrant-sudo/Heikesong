# V1 项目架构

## 架构目标

V1 只覆盖瑜伽垫识别、垫边环绕、用户定位、下犬式识别与响应、跟随用户方向、计时。算法、设备 SDK 和业务编排通过接口分离，使录像测试、Mock 测试与真机测试共用同一组需求编号和事件契约。

## 模块关系

```text
摄像头/录像
    │
    ▼
perception ──► core observations ──► behavior/session coordinator
  │                                       │
  ├─ yoga mat detector                    ├─ orbit controller
  ├─ user locator                         ├─ direction follower
  └─ downward-dog detector                └─ pose response
                                              │
                     safety gate ◄────────────┤
                                              ▼
                                  actions / robot adapter / camera

services/timer ──► session events ──► coordinator and test reports
```

## 目录与职责

| 模块 | V1 职责 | 主要输入 | 主要输出 |
|---|---|---|---|
| `core` | 稳定的数据结构、事件名和状态 | 无设备依赖 | Observation、DomainEvent |
| `perception` | 识别垫子、用户位置与下犬式 | 图像帧 | `MatObservation`、`UserObservation`、`PoseObservation` |
| `behavior` | 规划垫边环绕、用户方向跟随与动作编排 | 世界状态、计时事件 | 可取消的行为意图 |
| `actions` | 隔离拍照和机器人动作接口 | 经安全批准的动作请求 | 动作结果、照片引用 |
| `services` | 计时等无硬件业务能力 | 单调时钟、控制命令 | 计时快照和事件 |
| `safety` | 在任何移动前统一授权并可抢占 | 障碍、人员、连接和设备状态 | 允许、停止原因 |

## V1 主流程

1. 识别瑜伽垫并形成中心点与边界观察结果。
2. 安全检查通过后，机器狗在批准距离和速度内环绕瑜伽垫。
3. 识别用户位置及移动方向；垫子或用户丢失时取消对应移动。
4. 根据稳定后的用户方向更新跟随目标，抖动不应造成频繁转向。
5. 下犬式达到持续时间和置信度阈值后，生成一个关联 ID，同时触发模仿动作和拍照；冷却期内不重复触发。
6. 计时器独立记录开始、暂停、恢复、停止和到时，不依赖视频帧率或系统墙上时间。

## 可替换接口

- 感知模型只能通过 `perception/interfaces.py` 暴露结果，行为层不得直接调用某个模型框架。
- 机器狗和相机只能通过 `actions/interfaces.py` 调用；目标设备为 Vbot 大头 EDU，具体 Adapter 仅在正式接口清单完成后实现，发现阶段继续使用 Mock。
- 所有移动意图必须经过 `SafetySupervisor`，并实现取消路径。
- `correlation_id` 串联姿态识别、模仿动作、照片和报告，便于检查一次识别只触发一次响应。

## 增量扩展规则

新增功能应新建需求 ID、模块接口和测试用例，不复用或改写既有 ID 的含义。现有数据契约只允许向后兼容地增加可选字段；破坏性修改必须升版本。每次增量至少回归受影响模块、其上游感知、下游动作和安全抢占，详细规则见 `docs/testing/INCREMENTAL_TESTING.md`。
