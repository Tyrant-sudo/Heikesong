# V1 需求—测试追踪矩阵

状态说明：`Planned` 表示已纳入计划；`Blocked-by-SDK` 只用于需要真实设备且接口尚未确认的部分。

| 需求编号 | 需求摘要 | 优先级 | 主要测试编号 | 首选环境 | 初始状态 |
|---|---|---|---|---|---|
| BEH-001 | 安全区域闲逛 | 高 | TC-E2E-001 | SIM-MOCK / FIELD-YOGA | Planned |
| BEH-002 | 自主选择人物并靠近 | 高 | TC-BEH-001, TC-E2E-001 | SIM-MOCK / FIELD-YOGA | Planned |
| BEH-003 | 坐在用户旁并保持朝向 | 高 | TC-E2E-001 | HIL-SDK / FIELD-YOGA | Planned |
| BEH-004 | 用户躺下后趴卧 | 中 | TC-E2E-001 | OFFLINE-CV / HIL-SDK | Planned |
| BEH-005 | 伸手时头部靠近 | 高 | TC-E2E-001 | OFFLINE-CV / HIL-SDK | Planned |
| BEH-006 | Paw / 击掌 | 中 | TC-E2E-001 | HIL-SDK | Planned |
| BEH-007 | 用户换位置后重新跟随 | 高 | TC-BEH-002, TC-E2E-001 | SIM-MOCK / FIELD-YOGA | Planned |
| BEH-008 | 下犬式触发 Play-bow | 高 | TC-PER-003, TC-E2E-001 | OFFLINE-CV / HIL-SDK | Planned |
| BEH-009 | 安全环绕用户 | 中 | TC-E2E-001, TC-SAFE-001 | HIL-SDK / FIELD-YOGA | Planned |
| BEH-010 | 冷却后的随机打扰 | 中 | TC-E2E-001 | SIM-MOCK | Planned |
| PER-001 | 人体存在检测 | 高 | TC-PER-001 | OFFLINE-CV | Planned |
| PER-002 | 人体相对位置检测 | 高 | TC-BEH-001 | OFFLINE-CV / HIL-SDK | Planned |
| PER-003 | 高位/低位判断 | 高 | TC-PER-002 | OFFLINE-CV | Planned |
| PER-004 | 下犬式识别 | 高 | TC-PER-003 | OFFLINE-CV | Planned |
| PER-005 | 伸手检测 | 中 | TC-E2E-001 | OFFLINE-CV | Planned |
| ANO-001 | 疑似倒地或异常静止 | 中 | TC-SAFE-001 | OFFLINE-CV / SIM-MOCK | Planned |
| SAFE-001 | 人距过近立即停止 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-002 | 障碍物停止或重规划 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-003 | 语音“停”中断行为 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-004 | 机器人姿态异常保护 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-005 | 动作超时返回安全状态 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-006 | 低电量禁止新移动互动 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| SAFE-007 | 连接中断自动停止 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |
| CAM-001 | 人体保持在画面内 | 高 | TC-CAM-001 | OFFLINE-CV / HIL-SDK | Planned |
| CAM-002 | 静止稳定录像 | 高 | TC-CAM-001 | HIL-SDK / FIELD-YOGA | Planned |
| CAM-003 | 低速移动录像 | 中 | TC-CAM-001 | HIL-SDK / FIELD-YOGA | Planned |
| SYS-001 | 统一行为状态机 | 必须 | TC-E2E-001 | SIM-MOCK | Planned |
| SYS-002 | Safety Override 抢占 | 必须 | TC-SAFE-001 | SIM-MOCK / HIL-SDK | Planned |

## 维护规则

- 修改 `function.md` 时必须同步检查本表。
- 新需求先获得需求编号，再编写测试。
- 一个“必须”需求至少需要一个 Mock 测试和一个真机或现场测试。
- 自动化测试文件名应包含测试编号，例如 `test_safe_001_connection_loss.py`。
