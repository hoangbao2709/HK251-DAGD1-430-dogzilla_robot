# QR -> LiDAR/SLAM map flow

Tài liệu này mô tả luồng xử lý chức năng quét QR và ánh xạ QR lên map SLAM/LiDAR trong dự án Dogzilla, từ frontend đến backend.

## Mục tiêu

- Đọc frame camera từ robot.
- Detect QR trong ảnh camera.
- Tính vị trí tương đối của QR so với robot.
- Kết hợp QR với pose SLAM để đặt QR lên map.
- Hiển thị QR, scan points, robot pose và obstacle trên giao diện Autonomous Control.

## Tổng quan luồng

1. Frontend gọi các API QR và SLAM theo chu kỳ.
2. Backend lấy frame camera từ robot qua `ROSClient`.
3. Backend detect QR, ước lượng pose của QR và sinh payload chuẩn hóa.
4. Backend trả về:
   - danh sách QR đã detect,
   - vị trí QR để FE ghép vào map,
   - stream video có overlay QR,
   - state SLAM đã chuẩn hóa cho UI.
5. Frontend dùng `slamState.pose` + `qrPosition.position` để tính tọa độ QR trên map.
6. FE vẽ QR lên map SLAM theo hệ trục thế giới của map.

## Frontend

### File chính

- [frontend/app/autonomous/page.tsx](../frontend/app/autonomous/page.tsx)
- [frontend/app/lib/robotApi.ts](../frontend/app/lib/robotApi.ts)
- [frontend/app/autonomous/types.ts](../frontend/app/autonomous/types.ts)

### FE gọi những gì

`RobotAPI` định nghĩa các endpoint chính:

- `qrVideoFeedUrl()` -> `GET /control/api/robots/<robot_id>/qr/video-feed/`
- `qrState()` -> `GET /control/api/robots/<robot_id>/qr/state/`
- `qrPosition()` -> `GET /control/api/robots/<robot_id>/qr/position/`
- `slamState()` -> `GET /control/api/robots/<robot_id>/slam/state/`
- `slamMapUrl()` -> `GET /control/api/robots/<robot_id>/slam/map.png`

Trong `AutonomousControlPage`, FE polling định kỳ:

- QR state mỗi `700ms`
- QR position mỗi `700ms`
- SLAM state mỗi `1500ms`
- map image refresh mỗi `3000ms`

### FE hiển thị QR trên map

Frontend không tự detect QR. Nó chỉ nhận dữ liệu đã xử lý từ backend và ghép vào map.

Điểm quan trọng nhất là công thức từ QR relative pose sang world pose:

```ts
const yaw = pose.theta || 0;
const worldX =
  pose.x + Math.cos(yaw) * qrForward + Math.sin(yaw) * qrLateral;
const worldY =
  pose.y + Math.sin(yaw) * qrForward - Math.cos(yaw) * qrLateral;
```

Trong đó:

- `pose.x`, `pose.y`, `pose.theta` lấy từ `slamState.pose`
- `qrForward` lấy từ `qrPosition.position.forward_z_m`
- `qrLateral` lấy từ `qrPosition.position.lateral_x_m`

Nếu QR đã tồn tại trong `savedPoints`, FE không preview lại điểm đó trên map.

### FE tạo point từ QR/obstacle

Trong `createPointFromObstacle()`:

1. FE lấy tên point từ QR đầu tiên trong `qrState.items[0].text`.
2. Gọi `POST /points/from-obstacle/` để backend tạo point từ obstacle phía trước.
3. Sau đó log metric QR qua `POST /qr-metrics/`.
4. Reload lại danh sách point và SLAM state.

## Backend QR pipeline

### File chính

- [backend/control/services/qr_detector.py](../backend/control/services/qr_detector.py)
- [backend/control/services/qr_detect.py](../backend/control/services/qr_detect.py)
- [backend/control/views.py](../backend/control/views.py)
- [backend/control/services/models.py](../backend/control/services/models.py)
- [backend/control/services/overlay.py](../backend/control/services/overlay.py)

### 1) Lấy frame camera

`detect_qr_state_once(robot_id)` gọi:

- `ROSClient(robot_id).get_frame()`

`ROSClient.get_frame()` lấy ảnh từ endpoint camera của robot rồi decode sang `cv2` frame.

Nếu không lấy được frame thì backend trả về payload lỗi, không tiếp tục detect.

### 2) Detect QR

`detect_qr_items()` làm các bước sau:

1. Resize ảnh về `detect_width=640` nếu ảnh quá lớn.
2. Chuyển sang grayscale và blur nhẹ.
3. Decode QR bằng:
   - `pyzbar` nếu có sẵn
   - fallback sang `OpenCV QRCodeDetector` nếu `pyzbar/libzbar` không có
4. Lấy polygon/rect của QR.
5. Scale corner points về kích thước frame gốc.
6. Build ma trận camera hiệu dụng theo kích thước frame thực tế.
7. Gọi `cv2.solvePnP()` để ước lượng pose 3D của QR.
8. Tính:
   - `angle_deg`, `angle_rad`
   - `distance_m`
   - `lateral_x_m`
   - `forward_z_m`
   - `target_x_m`, `target_z_m`
   - `direction`

### 3) Quy ước tọa độ QR

Backend dùng QR size cố định:

- `QR_SIZE_M = 0.12`

Các giá trị tính ra:

- `forward_z_m`: khoảng cách phía trước robot tới QR
- `lateral_x_m`: lệch trái/phải
- `target_*`: điểm đích được đẩy ra xa QR thêm một khoảng an toàn

Công thức target:

- nếu QR quá gần, ép tối thiểu `min_target_distance_m = 0.65`
- nếu không, cộng thêm `push_m = 0.35`

### 4) Dựng payload trả về

`detect_qr_state_once()` trả về 2 lớp dữ liệu:

- `items`: danh sách QR đầy đủ
- `position_json`: QR đầu tiên, chuẩn hóa cho UI

`position_json` gồm:

- `detected`
- `qr.text`, `qr.type`, `qr.direction`
- `position.angle_deg`, `position.angle_rad`
- `position.distance_m`
- `position.lateral_x_m`, `position.forward_z_m`
- `target.x_m`, `target.z_m`, `target.distance_m`
- `image.center_px`, `image.corners`

### 5) Track QR state cho metric

`update_qr_tracking_state()` chỉ cập nhật trạng thái:

- `in_view`
- `current_text`

Nó không log success/attempt ở đây. Metric được log riêng qua `QRMetricView`.

## Backend SLAM/LiDAR pipeline

### File chính

- [backend/control/services/ros.py](../backend/control/services/ros.py)
- [backend/control/services/slam_payload.py](../backend/control/services/slam_payload.py)
- [backend/control/views.py](../backend/control/views.py)

### Lấy SLAM state

`SlamStateView` trả state từ:

- `ROSClient.get_slam_state_for_ui(include_scan_points=...)`

`ROSClient.get_slam_state_for_ui()` chọn:

- `get_slam_state()` nếu cần scan points
- `get_slam_state_light()` nếu không cần scan points

Sau đó nó chạy `build_slam_ui_state()` để chuẩn hóa payload cho FE.

### Chuẩn hóa scan points

`scan_points_from_raw_scan()`:

- đọc `scan.raw.samples`
- transform các sample scan sang hệ tọa độ map
- downsample số điểm scan để tránh payload quá nặng

Nếu không có raw samples, nó fallback sang `scan.points`.

### Tìm obstacle phía trước

`find_nearest_obstacle_ahead()`:

- lấy pose robot
- so điểm scan theo hướng trước robot trong một góc nhìn hẹp
- chọn điểm gần nhất làm `nearest_obstacle_ahead`

Kết quả này FE dùng để hiển thị obstacle hiện tại và để tạo point từ obstacle.

## Endpoint backend liên quan

### QR

- `GET /control/api/robots/<robot_id>/qr/state/`
- `GET /control/api/robots/<robot_id>/qr/position/`
- `GET /control/api/robots/<robot_id>/qr/video-feed/`
- `GET/POST /control/api/robots/<robot_id>/qr-metrics/`

### SLAM/LiDAR

- `GET /control/api/robots/<robot_id>/slam/state/`
- `GET /control/api/robots/<robot_id>/slam/map.png`
- `POST /control/api/robots/<robot_id>/command/lidar/`
- `POST /control/api/robots/<robot_id>/command/lidar/reset/`
- `POST /control/api/robots/<robot_id>/slam/clear/`
- `POST /control/api/robots/<robot_id>/slam/initial-pose/`

## Luồng thực tế khi người dùng mở trang Autonomous

1. FE load `AutonomousControlPage`.
2. FE đồng thời gọi:
   - QR state
   - QR position
   - SLAM state
   - control status
   - saved points
3. FE render:
   - camera QR stream
   - map SLAM
   - scan points
   - path
   - robot pose
   - QR preview nếu QR đang thấy và chưa lưu
4. Khi người dùng bấm tạo point từ obstacle:
   - FE dùng QR text làm tên point
   - backend lấy obstacle phía trước trong SLAM scan
   - backend tạo point trên map robot
   - FE cập nhật lại danh sách point và map

## Ghi chú triển khai

- Nếu `pyzbar/libzbar` không có, backend tự fallback sang OpenCV QR detector.
- `QRPositionView` chỉ trả `position_json`, còn `QRStateView` trả toàn bộ `items`.
- FE lấy `slam/map.png` để vẽ overlay trên ảnh map, không vẽ trực tiếp lên dữ liệu scan thô.
- `slamState.pose` là dữ liệu gốc để ghép vị trí QR từ camera sang world map.

## Tóm tắt ngắn

- Camera -> backend QR detector -> `qr/state` và `qr/position`
- SLAM service -> backend `slam/state` -> FE render map
- FE kết hợp `pose + QR offset` để đặt QR lên map
- Khi cần lưu point, FE gọi backend tạo point từ obstacle phía trước
