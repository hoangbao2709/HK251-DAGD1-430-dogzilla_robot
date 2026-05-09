# AI VOICE and QR Flowcharts

## 1. AI VOICE flow

```mermaid
flowchart TD
    A[User nhan mic hoac nhap text] --> B{Dung Web Speech API?}
    B -- Co --> C[startListening]
    C --> D[SpeechRecognition lang=vi-VN]
    D --> E[onresult cap nhat commandText]
    B -- Khong --> F[User tu nhap commandText]
    E --> G[sendVoiceCommand]
    F --> G
    G --> H{commandText rong?}
    H -- Co --> H1[setCommandError]
    H -- Khong --> I{robotAddr co hop le?}
    I -- Khong --> I1[setCommandError]
    I -- Co --> J[Frontend goi RobotAPI.textCommand]
    J --> K[POST /api/robots/:robotId/command/text/]
    K --> L[TextCommandView]
    L --> M[OpenRouter planner hoac fallback keyword]
    M --> N[tool_name + arguments]
    N --> O{Lenh thuoc nhom nao?}
    O --> O1[set_posture / play_behavior]
    O --> O2[goto_point / goto_waypoints]
    O --> O3[stop_navigation / rotation / reset_robot]
    O1 --> P[execute_mcp_tool]
    O2 --> P
    O3 --> P
    P --> Q[Khoi tao MCP client voi robot_mcp_server.py]
    Q --> R[call_tool tren robot]
    R --> S{Thanh cong?}
    S -- Co --> T[Tra result ve frontend]
    S -- Khong --> U[Tra error ve frontend]
    T --> V[setCommandResult hien thi ket qua]
    U --> W[setCommandError hien thi loi]
```

## 2. QR flow

```mermaid
flowchart TD
    A[Autonomous page mount] --> B[setInterval moi 700ms]
    B --> C[fetchQrState]
    B --> D[fetchQrPosition]
    B --> E[CameraPanel load qr/video-feed]

    C --> F[RobotAPI.qrState]
    D --> G[RobotAPI.qrPosition]
    E --> H[RobotAPI.qrVideoFeedUrl]

    F --> I[GET /api/robots/:robotId/qr/state/]
    G --> J[GET /api/robots/:robotId/qr/position/]
    H --> K[GET /api/robots/:robotId/qr/video-feed/]

    I --> L[QRStateView]
    J --> M[QRPositionView]
    K --> N[QRVideoFeedView]

    L --> O[detect_qr_state_once]
    M --> O
    N --> P[generate_qr_video_frames]

    O --> Q[ROSClient.get_frame]
    P --> R[ROSClient.get_fpv_url + VideoCapture]

    Q --> S[detect_qr_items]
    R --> T[detect_qr_items moi frame]

    S --> U{Co QR?}
    U -- Khong --> U1[Tra ok=false + empty position payload]
    U -- Co --> V[Tinh pose, angle, distance, target]
    V --> W[build_position_payload]
    W --> X[Tra items + position_json]

    T --> Y[draw_overlay]
    Y --> Z[Stream JPEG frames ve frontend]

    X --> AA[Frontend setQrState / setQrPosition]
    Z --> AB[CameraPanel hien thi QR video stream]
    AA --> AC[SidebarPanel + TopDownQrView]
    AA --> AD[Map overlay gan nhan QR len SLAM]
```

## 3. Quick notes

- `AI VOICE` frontend: `frontend/app/autonomous/page.tsx`
- `AI VOICE` API client: `frontend/app/lib/robotApi.ts`
- `AI VOICE` backend: `backend/control/views.py`, `backend/control/services/mcp_voice.py`
- `QR` frontend: `frontend/app/autonomous/page.tsx`
- `QR` backend: `backend/control/views.py`, `backend/control/services/qr_detect.py`, `backend/control/services/qr_detector.py`
