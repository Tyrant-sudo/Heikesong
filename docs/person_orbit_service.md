# 人员环绕服务接口

`vbot_person_orbit_service_node.py` 是常驻 ROS 2 节点，供其他进程通过标准
ROS 2 服务调用。调用方不需要导入项目私有消息包。

## 接口

| 名称 | 类型 | 说明 |
|---|---|---|
| `/heikesong/person_orbit/start` | `std_srvs/srv/Trigger` | 启动一次人员环绕 |
| `/heikesong/person_orbit/stop` | `std_srvs/srv/Trigger` | 请求停止并清零速度 |
| `/heikesong/person_orbit/get_status` | `std_srvs/srv/Trigger` | 在 `message` 中返回 JSON 状态 |
| `/heikesong/person_orbit/status` | `std_msgs/msg/String` | 持久化发布 JSON 状态与进度 |

同一时间只接受一个环绕任务。节点内部依次执行垫上人员选择、雷达测距、
接近、视觉闭环环绕、清零速度和恢复 `FIXED_STAND`。

## 参数

| 参数 | 默认值 | 范围 |
|---|---:|---:|
| `direction` | `1` | `1` 向左环绕，`-1` 向右环绕 |
| `orbit_duration_s` | `6.8` | `1.0` 至 `60.0` |
| `target_distance_m` | `0.60` | `0.45` 至 `0.90` |
| `hard_stop_distance_m` | `0.30` | 不小于 `0.25` 且小于目标距离 |
| `maximum_approach_s` | `20.0` | `1.0` 至 `60.0` |

参数可通过 ROS 2 标准参数服务修改，不需要重启节点。

## 命令行调用

```bash
ros2 service call /heikesong/person_orbit/start std_srvs/srv/Trigger '{}'
ros2 service call /heikesong/person_orbit/get_status std_srvs/srv/Trigger '{}'
ros2 service call /heikesong/person_orbit/stop std_srvs/srv/Trigger '{}'
```

## Python 进程调用

```python
import rclpy
from std_srvs.srv import Trigger

rclpy.init()
node = rclpy.create_node("yoga_session")
client = node.create_client(Trigger, "/heikesong/person_orbit/start")
client.wait_for_service(timeout_sec=3.0)
future = client.call_async(Trigger.Request())
rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
response = future.result()
if not response.success:
    raise RuntimeError(response.message)
```

`start` 返回成功只表示任务已被接收。完成、终止和失败原因通过
`/heikesong/person_orbit/status` 或 `get_status` 获取。
