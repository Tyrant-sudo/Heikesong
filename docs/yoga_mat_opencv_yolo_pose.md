# 固定颜色瑜伽垫 + YOLO Pose 识别方案

## 目标

在 Vbot 视觉链路中，以“先检索瑜伽垫区域，再做人姿态检测”为主流程：
- 固定一张高饱和、背景不常见的瑜伽垫颜色（建议高亮黄/绿/粉）；
- 用 OpenCV 从图像中稳定提取瑜伽垫 ROI；
- 在 ROI 内运行 YOLO Pose，输出人体关键点与姿态结果；
- 只将“位于垫子区域内/附近”的人体作为后续行为决策输入。

## 一、OpenCV 垫子检测（固定颜色）

### 输入

- 相机 BGR 图像，帧率建议 15~30 FPS
- 已知的目标垫子颜色 `HSV` 阈值区间（按现场实拍标定）
- 目标瑜伽垫实物尺寸为 `80 cm × 180 cm`，真实长宽比为 `2.25`

### 流程

1. 去畸变与颜色空间转换
   优先使用相机标定参数去畸变，再执行：
   `BGR -> HSV`
2. 阈值分割
   `mask = cv2.inRange(hsv, lower_hsv, upper_hsv)`
3. 去噪
   `erode -> dilate`（开运算）去除小噪点
4. 提取大连通域
   取 `findContours` 最大轮廓，面积阈值 `area > A_min`
5. 几何约束
   用四边形或 `minAreaRect` 拟合垫子，结合面积和实物长宽比 `2.25` 过滤目标。画面中的轴对齐外接框会受透视、裁切和镜头畸变影响，不能直接要求其长宽比等于 `2.25`。
6. ROI 输出
   生成稳定 ROI（带 5~10% margin），用于后续 YOLO Pose 推理

### 关键参数（初始默认）

- `A_min_ref = 5000` 像素（参考分辨率 640×480）；实际阈值按图像像素数等比例缩放
- `ratio_min = 0.25`、`ratio_max = 5.0`
- H/S/V 阈值：
- 本次肉粉紫色垫现场标定值：`lower=[18, 10, 90], upper=[32, 38, 160]`
- 原始高饱和紫色候选值：`lower=[125, 50, 60], upper=[168, 160, 230]`
- 黄色：`lower=[18, 100, 100], upper=[40, 255, 255]`
- 绿色：`lower=[40, 80, 70], upper=[85, 255, 255]`

> 说明：颜色阈值是首次标定项，先在静态采集图像上跑一次标定，再冻结到配置文件，后续尽量不要频繁改。

### 肉色紫色快速标定（一次性建议）

在一张包含瑜伽垫的静态图上采样 100~200 个垫子区域像素，先取 HSV 均值再扩展：

```bash
python - <<'PY'
import cv2, numpy as np
img = cv2.imread("tests/reports/calib_mat_sample.jpg")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# 假设你已经手动给出 ROI: x1,y1,x2,y2
x1,y1,x2,y2 = 100, 100, 260, 220
roi = hsv[y1:y2, x1:x2].reshape(-1, 3)
lo = np.percentile(roi, [2, 2, 2], axis=0).astype(int)
hi = np.percentile(roi, [98, 98, 98], axis=0).astype(int)
print("color_hsv_lower:", lo.tolist())
print("color_hsv_upper:", hi.tolist())
PY
```

## 二、YOLO Pose 识别人

### 运行策略

- 使用 `ultralytics` 官方 pose 模型（例如 `yolo11n-pose` 或已训练定制模型）；
- 推理输入优先用 `mat_roi`，无 ROI 时退化为整帧；
- 只保留 `class=person` 的检测结果；
- 对检测框置信度设置 `pose_score >= 0.4`（可微调）。

### 融合规则

- 若脚踝、膝、髋或人体框底部中心落在去畸变后的垫子多边形内，判为“在垫子上”；
- 坐姿或遮挡场景下，若人体框与垫子 `ROI` 的 IoU `>= 0.10`，也判为相关；
- 使用连续多帧滞回避免 IoU 在阈值附近时反复跳变；
- 对相关人体输出关键点、姿态等级、是否落在安全区。

## 三、状态机（最小闭环）

- `STATE_DETECT_MAT`
  - 成功找到垫子后写入 `mat_bbox` 与 `mat_roi`
- `STATE_DETECT_PERSON`
  - 在 `mat_roi` 内跑 YOLO Pose
- `STATE_ON_MAT`
  - 至少一个人的关键点检测满足：`person_score >= 0.4 && overlap_ok`
- `STATE_LOST`
  - 连续 N 帧未检到垫子或人时降级为观察态，不驱动动作

## 四、部署与验证（可执行）

### 1. 离线验证（本机）

1. 采集 100~300 帧样本图像
   - 至少 30% 无垫子、30% 有垫子、40% 有人站/蹲/俯身在垫子上
2. 运行标注脚本（示意）：

```bash
python - <<'PY'
import cv2, json, os

img_dir = "data/raw_frames"
out = []
for fn in sorted(os.listdir(img_dir)):
    img = cv2.imread(f"{img_dir}/{fn}")
    # TODO: run_color_mat_and_pose(img)
    out.append({
        "file": fn,
        "mat_detected": True,
        "person_detected": True,
        "on_mat": True,
        "iou": 0.82
    })
with open("tests/reports/mat_pose_eval.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved: tests/reports/mat_pose_eval.json")
PY
```

3. 验收指标：
- 垫子检测召回率 `>= 0.95`
- 垫子框与人工标注 IoU `>= 0.85`（可视情况放宽）
- 人体检测召回率 `>= 0.90`
- 在垫子上的正确关联率（person in mat）`>= 0.85`

### 2. 联机验证（狗上跑）

1. 启动感知与采集链路后运行探针记录（沿用现有 `/perception` 通道）；
2. 观察日志中包含：
   - 检测垫子框（坐标/尺寸/置信度）
   - 人体框 + 关键点
   - on_mat 判定结果
3. 连续 20 秒内执行：
   - 静止在垫子边缘（应判定为在垫子内）
   - 完全离开垫子（应快速退回 LOST）
   - 不同光照下重复一次

### 3. 回归条件（每次上线前）

- 无人值守 10 秒：不得持续发起动作指令（必须先稳定进入 `STATE_ON_MAT`）
- 无垫子场景不得触发“在垫子上”状态
- 关键日志必须包含 `mat_bbox` / `person_boxes` / `on_mat` 字段

### 4. 2026-08-27 真机验证结果（垫子检测未通过）

- 设备：Vbot EDU，SSH `192.168.126.2:22`，相机请求启用 `undistort=true`
- 机器人 Pose 模型：`/app/perception/models/s100/yolo11n_pose_nashe_640x640_nv12.hbm`
- 图像：`480×270`；面积阈值由参考值缩放为 `2109.375 px²`
- 瑜伽垫：检测面积 `4903.5 px²`，检测框 `[327, 160, 153, 89]`
- 人体：置信度 `0.9096`，17 个关键点
- Pose：人体置信度与 17 个关键点输出通过；现场观察确认人确实在垫子上
- 垫子：现场复核发现颜色轮廓只覆盖垫子局部，检测框位置不准确；IoU 与 `on_mat=true` 结果因此不能作为有效验收证据
- 结论：相机与 YOLO Pose 通过，OpenCV 垫子边界和人在垫上融合判定未通过；在完成多角度人工标注前不得部署为生产服务
- 证据：`tests/reports/v1_photo_artifacts/vbot_mat_pose_final_20260827_231310_result.json` 和同名前缀的 `overlay.jpg`
- 后续采集：`tests/reports/yoga_mat_calibration/20260827_231959/`，共 301 张去畸变图像

## 五、配置化建议（最小字段）

在配置文件中建议加入：

```yaml
vision:
  mat:
    physical_size_cm: [80, 180]
    color_hsv_lower: [18, 10, 90]
    color_hsv_upper: [32, 38, 160]
    min_area_px_at_640x480: 5000
    aspect_ratio_range: [0.25, 5.0]
    margin: 0.08
  pose:
    model_path_robot: "/app/perception/models/s100/yolo11n_pose_nashe_640x640_nv12.hbm"
    model_path_workstation: "models/yolo11n-pose.pt"
    person_score_thr: 0.40
    mat_overlap_iou_thr: 0.10
```

## 六、验收结论输出模板

- 文件：`tests/reports/mat_pose_eval.json`
- 字段：`mat_detected`, `mat_bbox`, `person_detected`, `person_bbox`, `pose_ok`, `on_mat`, `fps`
- 在 `docs/testing/forms/V1_TEST_RECORD.md` 记录本次验证版本、场景、脚本、采样数、通过率。

## 七、2026-08-28 肉粉紫色瑜伽垫重新标定

### 检测方法

现场照片表明目标垫是低饱和肉粉紫色，灰色地面也有暖色偏移。旧的 HSV 区间会选择同色地面或只覆盖垫子局部，因此改用以下保守组合：

1. 在去畸变图像的地面区域内做 CIE Lab 阈值分割；
2. 使用开、闭运算去除噪声并连接垫子区域；
3. 要求候选轮廓面积、凸包实心度和四边形拟合同时通过；
4. 候选接触左右边界或底边时按 `clipped` 拒绝；
5. 单帧结果只能作为感知候选，连续 10 帧稳定后才允许生成禁行区。

现场标定值记录在 `config/perception/yoga_mat_color.yaml`：

```yaml
lab_lower: [130, 131, 125]
lab_upper: [180, 140, 134]
ground_top_fraction: 0.58
min_area_fraction: 0.0045
min_solidity: 0.84
```

实现文件：

- `src/heikesong/perception/yoga_mat_color.py`
- `tools/verify_yoga_mat_color.py`
- `tests/unit/test_yoga_mat_color.py`

### 离线实拍回归

- 输入：机器人前摄像头去畸变 JPEG，实际分辨率 `480x270`；
- 完整可见样本：13 张，覆盖横向、纵向和两条对角线，13 张全部检出；
- 拒绝样本：5 张，覆盖无垫、底边裁切和人员遮挡，5 张全部拒绝；
- 合成回归：3 项通过，覆盖完整四边形、无垫和底边裁切；
- 证据目录：`tests/reports/yoga_mat_opencv_validation/20260828_base_angles/`。

以上数据来自同一现场和同一轮颜色标定，只能证明第一版规则在当前环境可用，不能替代独立验证集。改变灯光、地面或垫子颜色后必须重新标定并复跑误检测试。

### 机器人侧烟测

- 持久部署目录：`/userdata/vbot/vbot_dev/heikesong_perception`；
- 机器人运行时：OpenCV `4.11.0`、NumPy `1.26.4`；
- 未注册 systemd 服务，未修改现有 ROS 2 感知服务，未发送运动命令；
- 当前实时帧中垫子右侧和近端超出画面，检测器按 `clipped` 正确拒绝；
- 证据目录：`tests/reports/yoga_mat_robot_validation/20260828_131951/`。

重新调整垫子位置后，机器人本机以 0.5 秒间隔连续采集 10 帧：

- 10/10 帧检出完整四边形；
- 启发式置信评分范围 `0.9681` 至 `0.9790`；
- 首帧和末帧人工复核均贴合整张垫子，没有扩展到周围地面；
- 证据目录：`tests/reports/yoga_mat_robot_validation/20260828_132348/`。

当前结论：离线基础角度回归、裁切拒绝、机器人本机执行和连续 10 帧完整垫子检测通过。尚未把像素四边形投影到地面坐标，也未接入导航禁行区，因此不得据此启动自主绕行。

首次部署前机器人上不存在同名目录，所以没有旧版本可恢复。回滚方式为停止后续测试进程并删除新目录 `/userdata/vbot/vbot_dev/heikesong_perception`；现有系统服务不需要恢复。
