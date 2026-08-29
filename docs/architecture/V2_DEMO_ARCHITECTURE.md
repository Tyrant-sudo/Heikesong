# V2 瑜伽演示架构

V2 在用户明确说“佳佳”后再说“瑜伽功能”或“瑜伽模式”时启动。未进入模式时，`/perception/poses` 只用于原有看人能力，不会触发 V2 动作。

## 输入与任务

佳佳原厂 `yolo_detector_node` 已在 `/perception/poses` 发布 `vision_msgs/msg/PoseDetection`，包含人体框和 17 个 COCO 关键点。V2 使用粗粒度规则，不部署额外姿态模型：

- 臀部明显高于肩和脚：下犬式候选；
- 肩、髋和脚近似水平：俯卧撑候选；
- 人体关键点位移连续低于阈值：情感支持候选；
- “结束啦”：当前任务安全完成后执行右侧击掌并退出模式。

下犬式、俯卧撑和“坐下看我”是三个平级任务。看人和取景属于底层能力，不是情感支持任务。

## 状态流

```text
IDLE
  -> 瑜伽功能/瑜伽模式
ACTIVE
  -> 视觉或语音任务
TASK_RUNNING
  -> 安全完成/恢复
ACTIVE
  -> 结束啦（或在 TASK_RUNNING 中登记待执行）
TASK_RUNNING(high five right)
  -> IDLE
```

语音和视觉进入同一个 `V2SessionCoordinator`。同一时刻只运行一个任务；同一连续视觉姿势只产生一次事件；动作执行期间不消费新的视觉候选。“结束啦”可在任务期间登记，待当前动作安全完成后进入击掌等待。

## 运行模式

`run_vbot_v2_demo.sh` 默认只执行识别、模式反馈和任务日志，不执行身体动作：

```bash
HEIKESONG_V2_ENABLE_MOTION=0 run_vbot_v2_demo.sh
```

真机单项通过并由观察员确认后才允许：

```bash
HEIKESONG_V2_ENABLE_MOTION=1 run_vbot_v2_demo.sh
```

动作模式仍通过 V1 已验证的上下文检查，要求急停未激活、机器人静止且导航速度为零。右侧击掌动作必须单独完成现场确认。
