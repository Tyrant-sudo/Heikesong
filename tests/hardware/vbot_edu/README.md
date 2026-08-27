# Vbot EDU 硬件测试

本目录固定使用设备测试版本 `0.1.0`，目标环境为 `HIL-VBOT-EDU`。

执行顺序：

1. `TC-HW-EDU-001`：确认型号、EDU 标识和版本快照。
2. `TC-HW-EDU-002`：枚举正式开发接口。
3. `TC-HW-EDU-003`：验证 V1 所需感知流。
4. `TC-HW-EDU-004`：先验证停止，再做最低速度运动。
5. `TC-HW-EDU-005`：验证拍照和去重。
6. `TC-HW-EDU-006`：验证断网、心跳和恢复。
7. `TC-HW-EDU-007`：需要外设时核对端口。
8. `TC-HW-EDU-008`：完成一次 V1 真机冒烟。

设备配置模板位于 `config/device/vbot_edu.yaml`。真实序列号、IP、凭据和包含个人信息的日志不得提交 Git；执行记录使用 `docs/testing/forms/VBOT_EDU_DEVICE_RECORD.md`。
