# 瑜伽垫地面投影与导航禁行区

## 目标与边界

本方案把完整可见的肉粉紫色瑜伽垫从前摄像头像素坐标转换到 SLAM `map` 坐标，并生成供本项目导航使用的禁行多边形和占用栅格。

Vbot 当前固件没有标准 Nav2/costmap，也没有可写入厂商导航器的禁行区接口。本文实现的门禁只约束发送到 `/heikesong/nav/cmd_vel_requested` 的项目自有运动请求；手机 App、厂商动作服务或其他节点直接发布的 `/vel_cmd` 不受该门禁保证。

## 坐标投影

机器人实际使用的去畸变标定来自 `/app_param/vita_calib_rectified.yaml`：

```yaml
image_size: [480, 270]
intrinsics: [162.14315136170416, 162.14315136170416, 239.5, 134.5]
camera_frame: stereo_left
world_frame: map
mat_size_m: [0.8, 1.8]
```

处理流程：

1. `ColorYogaMatDetector` 输出完整四边形；
2. 分别尝试长边和短边对应关系；
3. 使用 OpenCV IPPE 平面 PnP 求解候选位姿；
4. 通过实时 TF `map <- stereo_left` 转换到地图坐标；
5. 只接受正深度、重投影误差不超过 `3 px`、垫面法向与地图重力轴对齐度不低于 `0.85` 的解；
6. 先在图像平面筛选连续采样中的 10 个稳定角点帧，角点相对中位数最大漂移不超过 `4 px`；
7. 对稳定角点取平均后只执行一次 PnP 和 TF 转换，避免把像素噪声放大成地图坐标抖动。

实现：`src/heikesong/perception/ground_projection.py`。

## 禁行区

Vbot 官方站立尺寸为 `0.613×0.339 m`。任意朝向的机器人中心安全半径按站立外接圆约 `0.350 m` 计算，再加入 `0.050 m` 边缘余量，最终把垫子向外扩张 `0.400 m`。

发布 topic：

| Topic | 类型 | 用途 |
|---|---|---|
| `/heikesong/yoga_mat/polygon_map` | `geometry_msgs/PolygonStamped` | 原始垫子边界 |
| `/heikesong/yoga_mat/keepout_map` | `geometry_msgs/PolygonStamped` | 扩张后的机器人中心禁行区 |
| `/heikesong/yoga_mat/keepout_grid` | `nav_msgs/OccupancyGrid` | `0.05 m` 分辨率局部占用栅格 |
| `/heikesong/yoga_mat/status` | `std_msgs/String` | 稳定度和拒绝原因 |

实现：`src/heikesong/safety/keepout.py` 和 `tools/vbot_yoga_mat_keepout_node.py`。

## 运动命令门

`tools/vbot_keepout_cmd_gate_node.py` 订阅：

- `/heikesong/yoga_mat/keepout_map`；
- `/heikesong/nav/cmd_vel_requested`。

它通过实时 TF `map <- base_link` 获取机器人中心位姿，并在 `map` 坐标中积分预测短时轨迹。机器人中心在禁行区内，或预测轨迹与禁行区相交时，输出零速度。

默认输出 `/heikesong/nav/cmd_vel_safe`，不会控制机器人。只有经过现场运动验收后显式加入 `--enable-motion-output`，才会把门控结果发布到 `/vel_cmd`。所有瑜伽项目自主运动必须使用该入口，不能直接调用厂商运动 topic 绕过门禁。

## 2026-08-28 静态真机验证

- 连续稳定帧：`10/10`；
- 原始投影边长：约 `0.799×1.799 m`；
- 扩张禁行区边长：约 `1.599×2.599 m`；
- 垫面重力对齐度：`0.999694`；
- 最终采样 30 帧，其中 21 帧满足 `4 px` 图像稳定门限，选取最近 10 个内点；
- 10 个选定内点的最大角点偏差：`3.606 px`；
- 最终重投影 RMS：`0.546 px`；
- OccupancyGrid：`61×71`，分辨率 `0.05 m`；
- 穿越禁行区的隔离测试请求输出为全零；
- 测试前后 `/vel_cmd` 仍为原厂 4 个发布者，本项目未加入真实运动链；
- 未发送真实运动命令，未注册或启用系统服务。

投影证据：`tests/reports/yoga_mat_keepout/20260828_135643/keepout_report.json`。

TF 命令门证据：`tests/reports/yoga_mat_keepout/20260828_135731/hil_gate_validation.json`。

## 部署与回滚

机器人部署目录：`/userdata/vbot/vbot_dev/heikesong_perception`。

本次更新前备份：`/userdata/vbot/vbot_dev/heikesong_perception.backup_20260828_134353`。

当前没有开机服务，退出测试节点后不会在后台继续运行。回滚时先停止所有 `heikesong_*` 测试节点，再用备份目录恢复部署目录；不要改动厂商 ROS 2 服务和 `/app_param` 标定文件。
