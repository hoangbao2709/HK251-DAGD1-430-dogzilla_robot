export type SlamPoint = {
    x: number;
    y: number;
};

export type SlamPose = {
    x: number;
    y: number;
    theta: number;
};

export type SlamRenderInfo = {
    origin_x: number;
    origin_y: number;
    resolution: number;
    width_cells: number;
    height_cells: number;
};

export type SlamStatus = {
    slam_ok?: boolean;
    tf_ok?: boolean;
    planner_ok?: boolean;
    map_age_sec?: number;
    pose_age_sec?: number;
    lidar_running?: boolean;
};

export type SlamStateData = {
    pose?: SlamPose;
    scan?: {
        points?: SlamPoint[];
    };
    render_info?: SlamRenderInfo;
    status?: SlamStatus;
};

export type RobotTelemetry = {
    robot_connected?: boolean;
    battery?: number;
    fps?: number;
    system?: {
        cpu_percent?: number;
        ram?: string;
        disk?: string;
        ip?: string;
        time?: string;
    };
};

export type RobotStatusResponse = {
    name?: string;
    floor?: string;
    status_text?: string;
    water_level?: number;
    battery?: number;
    telemetry?: RobotTelemetry;
};

export type ControlStatusResponse = {
    lidar_running?: boolean;
    lidar?: {
        running?: boolean;
    };
};

export type QrItem = {
    text: string;
    qr_type: string;
    angle_deg: number;
    distance_m: number;
    lateral_x_m: number;
    forward_z_m: number;
    target_x_m: number;
    target_z_m: number;
    direction: string;
};

export type QrStateData = {
    ok?: boolean;
    items?: QrItem[];
};

export type QrPositionData = {
    detected?: boolean;
    qr?: {
        text?: string;
        type?: string;
        direction?: string;
    };
    position?: {
        angle_deg?: number;
        angle_rad?: number;
        distance_m?: number;
        lateral_x_m?: number;
        forward_z_m?: number;
    };
    target?: {
        x_m?: number;
        z_m?: number;
        distance_m?: number;
    };
    image?: {
        center_px?: { x?: number; y?: number };
        corners?: number[][];
    };
    render_hint?: {
        suggested_max_range_m?: number;
    };
    timestamp?: number;
};

export type MarkerPoint = {
    x: number;
    y: number;
    yaw?: number;
};

export type PointsResponse = Record<string, MarkerPoint>;

export type ApiEnvelope<T> = {
    success?: boolean;
    robot_id?: string;
    data?: T;
    result?: T;
    error?: string;
    log?: string;
};

export type MapViewMode = "lidar" | "slam";

export type KeyValueCard = {
    label: string;
    value: string;
};

export type QuickCommand = {
    label: string;
    value: string;
};
