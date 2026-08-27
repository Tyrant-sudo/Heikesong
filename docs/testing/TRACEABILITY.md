# V1 需求—测试追踪矩阵

状态说明：`Planned` 为已纳入；`Implemented` 表示已有最小实现与自动化测试；`Ready-for-EDU-HIL` 表示 Vbot EDU 型号已确认，但必须先完成实机版本与接口枚举。

| 需求编号 | 需求摘要 | 优先级 | 责任模块 | 主要测试编号 | 初始状态 |
|---|---|---|---|---|---|
| MAT-001 | 判断画面中是否存在目标瑜伽垫 | 高 | perception | TC-MAT-001, TC-MAT-002 | Planned |
| MAT-002 | 输出可用于规划的垫子中心和边界 | 高 | perception/core | TC-MAT-001, TC-BEH-001 | Planned |
| MAT-003 | 垫子丢失后取消依赖行为并重新确认 | 高 | behavior | TC-MAT-002, TC-SAFE-001 | Planned |
| PER-001 | 识别单个用户的位置及相对垫子区域 | 高 | perception | TC-PER-001 | Planned |
| PER-002 | 输出连续、带时间戳的用户移动方向 | 高 | perception/core | TC-PER-001, TC-BEH-002 | Planned |
| POSE-001 | 识别稳定保持的下犬式 | 高 | perception | TC-POSE-001 | Planned |
| POSE-002 | 对相似姿势、短暂姿势和持续姿势进行去抖与复位 | 高 | perception/behavior | TC-POSE-001, TC-ACT-001 | Planned |
| BEH-001 | 在瑜伽垫批准环带内完成一次安全环绕 | 高 | behavior | TC-BEH-001 | Planned |
| BEH-002 | 按稳定后的用户方向更新跟随目标 | 高 | behavior | TC-BEH-002 | Planned |
| ACT-001 | 下犬式确认后执行一次模仿动作 | 高 | actions/behavior | TC-ACT-001, TC-HW-EDU-004, TC-HW-EDU-008 | Ready-for-EDU-HIL |
| CAM-001 | 下犬式确认后拍摄一次照片 | 高 | actions | TC-ACT-001, TC-HW-EDU-005 | Ready-for-EDU-HIL |
| CAM-002 | 照片与姿态/动作共享关联 ID 并符合隐私策略 | 必须 | actions/core | TC-ACT-001 | Planned |
| TIM-001 | 支持开始、暂停、恢复、停止和到时 | 高 | services | TC-TIM-001 | Implemented |
| TIM-002 | 计时不受暂停时间和墙上时间跳变影响 | 高 | services | TC-TIM-001 | Implemented |
| SYS-001 | 协调 V1 状态且同一时刻只有一个运动行为 | 必须 | core/behavior | TC-E2E-001, TC-SAFE-001 | Planned |
| SAFE-001 | 人员过近或操作员停止时抢占移动 | 必须 | safety | TC-SAFE-001, TC-HW-EDU-004 | Ready-for-EDU-HIL |
| SAFE-002 | 障碍、目标丢失或连接中断时停止，不自动续跑旧动作 | 必须 | safety/behavior | TC-SAFE-001, TC-MAT-002, TC-HW-EDU-006 | Ready-for-EDU-HIL |
| DEV-EDU-001 | 确认 Vbot 大头 EDU 身份与完整版本快照 | 必须 | device | TC-HW-EDU-001 | Ready-for-EDU-HIL |
| DEV-EDU-002 | 取得与固件匹配的正式开发包、文档和许可证 | 必须 | device | TC-HW-EDU-002 | Ready-for-EDU-HIL |
| DEV-EDU-003 | 冻结中间件、接口、QoS、单位和坐标系清单 | 必须 | device/core | TC-HW-EDU-002 | Ready-for-EDU-HIL |
| DEV-EDU-004 | 验证相机、深度、雷达和姿态数据流 | 高 | device/perception | TC-HW-EDU-003 | Ready-for-EDU-HIL |
| DEV-EDU-005 | 验证运动控制权、限速命令、取消和停止 | 必须 | device/safety | TC-HW-EDU-004 | Ready-for-EDU-HIL |
| DEV-EDU-006 | 验证单帧拍照、关联 ID 和失败处理 | 高 | device/actions | TC-HW-EDU-005 | Ready-for-EDU-HIL |
| DEV-EDU-007 | 验证网络、心跳、失联停止和重连 | 必须 | device/safety | TC-HW-EDU-006 | Ready-for-EDU-HIL |
| DEV-EDU-008 | 核对外设、供电和通信端口 | 中 | device | TC-HW-EDU-007 | Ready-for-EDU-HIL |
| DEV-EDU-009 | 通过 Vbot EDU 完成 V1 HIL 冒烟 | 高 | device/system | TC-HW-EDU-008 | Planned |

## 维护规则

- 新需求先分配新编号，再实现与编写测试；已发布编号不得改义或复用。
- 一个“必须”需求至少有一个 Mock 测试和一个真机/现场测试；实机资料或门禁未满足时明确标记 `Blocked`。
- 自动化文件名应包含测试编号，例如 `test_tim_001_pause_resume.py`。
- 需求、测试、配置、代码或设备版本变化时，同步更新测试批次记录。
