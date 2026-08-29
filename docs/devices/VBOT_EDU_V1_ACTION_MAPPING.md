# Vbot EDU V1 动作与反馈映射

本表记录 2026-08-28 对设备 `192.168.126.2` 的只读接口和资源核对结果。资源存在、服务返回成功和真机动作通过是三个不同门槛。

| V1 能力 | Vbot EDU 候选接口或资源 | 当前状态 | 放行条件 |
|---|---|---|---|
| 下犬式组合 | 用户资源 `PILATES_D_ONCE_50hz.npz` + `PILATES_D_ONCE.csv`，由 `vbot_edu_downward_dog_once.json` 编排；结束后强制 `FIXED_STAND` | HIL Pass | 399 帧版本已由观察员确认只做一次；请求 `V1-HIL-DOWNDOG-RECOVERY-1787911676` 返回 `SUCCESS`，随后稳定进入 `FIXED_STAND` |
| 俯卧撑 | `actions/PUSHUP.json`，身体策略 `PUSHUP_50hz.npz`，头部轨迹 `PUSHUP.csv` | Controller HIL pass / visual confirmation pending | 请求 `V1-HIL-PUSHUP-1787909743` 返回 `SUCCESS` 并恢复静止；等待观察员确认形态 |
| 坐下/趴下看人 | `idle/SIT_WITHHEAD.json`，身体和头部由同一厂商动作编排 | HIL Pass | 请求 `V1-HIL-SITHEAD-1787909955` 返回 `SUCCESS`，恢复静止，观察员确认效果可用 |
| 拍照 | `/get_jpeg_images`，请求 960x540、质量 90、去畸变 JPEG；设备实际返回 1280x720 | HIL Pass | 语音请求 `VOICE-TAKE_PHOTO-4250354df9` 已原子落盘并写入 `manifest.jsonl`；SHA-256 为 `e34bfc72dbbeeaa38b488870c9680972e5c05c1347dd57c2a246796ee607a2a5` |
| 眨眼后闪屏 | `/display_node/play_emotion` 的 `000_blink_once`，随后 `/display_node/display_imgs` 显示单帧短闪 | Control-plane Pass | 现场目视确认时长、亮度和恢复默认表情 |
| 开心动作 | 非跳跃的 `idle/HAPPINESS.json` | Bridge integrated | 通过 `--enable-body-action` 受控执行；现场确认动作幅度和稳定恢复后冻结 |
| 启动口令 | 本地 Sherpa-ONNX 识别“佳佳”，在 10 秒窗口内接受一个注册命令 | Implemented | 唤醒时眨眼并播放短提示音，命令按名称独立冷却 |
| 开始播报 | `/set_speak`，`HUMAN_VOICE`，文本“瑜伽开始了” | Control-plane Ready | 现场确认可听度，并等待 TTS 完成通知后结束交互 |

## 已确认限制

- `PILATES_D` 的低层 `pre_check=true` 在当前固件上仍触发姿态转换并最终安全趴卧，不能视为无运动检查。
- 单次下犬式保留原厂 `PILATES_D` 首次进入动作的 199 帧，并拼接原厂最后 200 帧返回站立尾段；身体拼接最大位置差约 `0.00078`、速度差约 `0.138`，头部拼接位置和速度完全一致，原厂文件未被覆盖。
- `action_sit_from_phone.json` 后再启动独立头部跟踪会触发机器人重新站立，因此正式映射改用同时占用腿部和头部资源的 `idle/SIT_WITHHEAD.json`。
- 动作服务返回“accepted”仅表示异步受理；模块必须等待相同 `request_id` 的 `rcp_status.last_outcome=SUCCESS` 且机器人恢复静止，才能记录完成。
- 相机响应在有效 JPEG 的 `FFD9` 后包含 6 个零填充字节；模块只在校验 `FFD8` 和 `FFD9` 后裁掉传输填充，并在清单中记录原始与有效长度。
- 离线模式未产生“瑜伽”命令事件；在线模式能正确理解瑜伽请求，但直接进入通用 Agent，没有发布 `/speech/command_word`。
- 2026-08-28 现场听到通用 Agent 回复“没法陪你做瑜伽动作……”，该结果证明在线 ASR 可用，但属于路由失败，不是 V1 成功反馈。
- 当前正确入口为“佳佳”后在 10 秒内说注册命令；不再依赖通用 Agent 的自由对话路由。
- 所有动作必须通过编排层去重，并在失败、超时或停止时禁止后续成功播报。
- 当前设备的 `vbot` 用户为 `Linger=no` 且没有 sudo，用户级 systemd 会在 SSH 退出时停止。现场改用带 `flock` 和崩溃重启循环的 `run_vbot_voice_person_tracker_supervisor.sh`；已验证 SSH 断开重连后 PID 保持不变。该方案不能跨整机重启，管理员仍需一次性执行 `loginctl enable-linger vbot` 才能恢复 systemd 开机常驻。
- 正式开机自启改用系统级 `heikesong-voice-person-tracker.service`，安装、状态检查、重启验收和停用步骤见 `VBOT_EDU_VOICE_AUTOSTART.md`。安装后不再并行启动临时 supervisor。
