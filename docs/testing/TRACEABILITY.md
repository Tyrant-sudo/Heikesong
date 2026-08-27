# V1 需求—测试追踪矩阵

状态说明：`Planned` 为已纳入；`Implemented` 表示已有最小实现与自动化测试；`Blocked-by-SDK` 仅用于真实设备部分，离线部分仍可推进。

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
| ACT-001 | 下犬式确认后执行一次模仿动作 | 高 | actions/behavior | TC-ACT-001 | Blocked-by-SDK |
| CAM-001 | 下犬式确认后拍摄一次照片 | 高 | actions | TC-ACT-001 | Blocked-by-SDK |
| CAM-002 | 照片与姿态/动作共享关联 ID 并符合隐私策略 | 必须 | actions/core | TC-ACT-001 | Planned |
| TIM-001 | 支持开始、暂停、恢复、停止和到时 | 高 | services | TC-TIM-001 | Implemented |
| TIM-002 | 计时不受暂停时间和墙上时间跳变影响 | 高 | services | TC-TIM-001 | Implemented |
| SYS-001 | 协调 V1 状态且同一时刻只有一个运动行为 | 必须 | core/behavior | TC-E2E-001, TC-SAFE-001 | Planned |
| SAFE-001 | 人员过近或操作员停止时抢占移动 | 必须 | safety | TC-SAFE-001 | Blocked-by-SDK |
| SAFE-002 | 障碍、目标丢失或连接中断时停止，不自动续跑旧动作 | 必须 | safety/behavior | TC-SAFE-001, TC-MAT-002 | Blocked-by-SDK |

## 维护规则

- 新需求先分配新编号，再实现与编写测试；已发布编号不得改义或复用。
- 一个“必须”需求至少有一个 Mock 测试和一个真机/现场测试；真机不可用时明确标记阻塞。
- 自动化文件名应包含测试编号，例如 `test_tim_001_pause_resume.py`。
- 需求、测试、配置、代码或设备版本变化时，同步更新测试批次记录。
