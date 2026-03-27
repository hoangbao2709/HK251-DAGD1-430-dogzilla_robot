def compute_line_errors(x_bottom, x_mid, x_top, image_center_x):
    e_lat = None
    e_heading = None
    e_mix = None
    status = "NO_LINE"

    valid_count = sum(v is not None for v in [x_bottom, x_mid, x_top])

    if valid_count == 0:
        return {
            "status": "NO_LINE",
            "e_lat": None,
            "e_heading": None,
            "e_mix": None,
        }

    if x_bottom is not None:
        e_lat = x_bottom - image_center_x

    if x_bottom is not None and x_top is not None:
        e_heading = x_top - x_bottom
    elif x_bottom is not None and x_mid is not None:
        e_heading = x_mid - x_bottom
    elif x_mid is not None and x_top is not None:
        e_heading = x_top - x_mid

    if e_lat is not None and e_heading is not None:
        e_mix = 0.7 * e_lat + 0.3 * e_heading
        status = "TRACKING"
    elif e_lat is not None:
        e_mix = e_lat
        status = "PARTIAL_TRACKING"
    else:
        status = "WEAK_TRACKING"

    return {
        "status": status,
        "e_lat": e_lat,
        "e_heading": e_heading,
        "e_mix": e_mix,
    }