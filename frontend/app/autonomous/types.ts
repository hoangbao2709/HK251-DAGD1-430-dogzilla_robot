export type SlamPoint = {
    x: number;
    y: number;
};

export type SlamObstacle = SlamPoint & {
    dist: number;
};

export type SlamPose = {
    ok?: boolean;
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
        ok?: boolean;
        points?: SlamPoint[];
    };
    goal?: {
        x?: number;
        y?: number;
        yaw?: number;
    };
    paths?: {
        a_star?: SlamPoint[];
    };
    render_info?: SlamRenderInfo;
    status?: SlamStatus;
    nearest_obstacle_ahead?: SlamObstacle | null;
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
    camera_distance_m?: number | null;
    lidar_distance_m?: number | null;
};

export type QrStateData = {
    ok?: boolean;
    items?: QrItem[];
    timestamp?: number;
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
        distance_source?: "camera" | "lidar" | string;
    };
    target?: {
        x_m?: number;
        z_m?: number;
        distance_m?: number;
        distance_source?: "camera" | "lidar" | string;
    };
    camera_position?: {
        angle_deg?: number;
        angle_rad?: number;
        distance_m?: number;
        lateral_x_m?: number;
        forward_z_m?: number;
    };
    lidar?: {
        ok?: boolean;
        source?: string;
        reason?: string;
        distance_m?: number;
        x?: number;
        y?: number;
        bearing_rad?: number;
        bearing_error_rad?: number;
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

export type PatrolPointResult = {
    point: string;
    status: string;
    attempts: number;
    started_at?: number | null;
    finished_at?: number | null;
    reach_time_sec?: number | null;
    distance_on_finish?: number | null;
    message?: string;
};

export type PatrolMission = {
    mission_id: string;
    robot_id: string;
    route_name: string;
    points: string[];
    wait_sec_per_point: number;
    max_retry_per_point: number;
    skip_on_fail: boolean;
    status: string;
    current_index: number;
    started_at?: number | null;
    finished_at?: number | null;
    results?: PatrolPointResult[];
};

export type PatrolStatusResponse = {
    success?: boolean;
    robot_id?: string;
    running?: boolean;
    mission?: PatrolMission | null;
};

export type ApiEnvelope<T> = {
    success?: boolean;
    robot_id?: string;
    data?: T;
    result?: T;
    error?: string;
    log?: string;
};

export type MapMode = "view" | "navigate";
export type NavPlacementMode = "goal" | "initialPose";
export type KeyValueCard = {
    label: string;
    value: string;
};

export type QuickCommand = {
    label: string;
    value: string;
};
