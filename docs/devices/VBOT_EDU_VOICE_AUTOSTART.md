# Vbot EDU 语音功能开机自启

本流程使“佳佳”唤醒、瑜伽反馈、动作口令和拍照入口在机器狗完整重启后自动恢复。动作和音频仍使用 `/userdata/vbot/.local/share/heikesong` 中已经验收的文件。

## 一次性安装

安装必须由具有 `sudo` 权限的管理员执行。普通 `vbot` 账户不能写入 `/etc/systemd/system`。

```bash
cd /path/to/Heikesong
sudo bash tools/install_vbot_voice_autostart.sh
```

安装脚本会校验 `vbot` 用户和语音启动脚本是否存在，然后安装并立即启动 `heikesong-voice-person-tracker.service`。

## 状态与日志

```bash
sudo systemctl status heikesong-voice-person-tracker.service
sudo journalctl -u heikesong-voice-person-tracker.service -n 100 --no-pager
```

预期状态为 `active (running)`。服务异常退出后等待 5 秒自动重启。

## 完整重启验收

1. 让机器狗保持安全静止并执行正常关机或重启。
2. 等待系统、网络和原厂 ROS 2 服务启动完成。
3. 不通过 SSH 手工启动任何 Heikesong 进程，直接检查服务状态。
4. 依次验证“佳佳”、 “瑜伽功能”、眨眼、提示音和“瑜伽开始了”。
5. 在观察员确认环境安全后，分别验证下犬式、俯卧撑、坐下/趴下看人和拍照。
6. 检查日志中没有重复进程、连续崩溃或动作重复触发。

## 停用与恢复

临时停止：

```bash
sudo systemctl stop heikesong-voice-person-tracker.service
```

取消开机启动：

```bash
sudo systemctl disable --now heikesong-voice-person-tracker.service
```

重新启用：

```bash
sudo systemctl enable --now heikesong-voice-person-tracker.service
```

系统级服务启用后，不要再手工启动 `run_vbot_voice_person_tracker_supervisor.sh`。systemd 只保证其管理的服务实例唯一，无法阻止手工启动第二个语音进程；同时保留两套守护方式会争用麦克风和 ROS 2 接口。
