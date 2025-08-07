from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import math


def analyze_gaze_data(
    face_landmarks: Optional[List[Dict]] = None,
    euler_angles: Optional[Dict[str, Optional[float]]] = None,
    config: Optional[Dict] = None,
) -> Tuple[bool, float, Dict]:
    """
    Determine if the user is looking away based on provided head pose and/or landmarks.

    Heuristic approach:
    - Prefer head pose (Euler angles) if available.
    - Fallback to basic eye corner vector heuristic if key landmarks exist.

    Returns: (looking_away, confidence, metrics)
    """

    cfg = {
        "yaw_threshold_deg": 20.0,
        "pitch_threshold_deg": 20.0,
        "roll_threshold_deg": 35.0,
        "min_confidence": 0.2,
    }
    if config:
        cfg.update(config)

    looking_away = False
    confidence = 0.0
    metrics: Dict = {"method": None}

    # 1) Euler-angle based decision
    if euler_angles is not None:
        yaw = euler_angles.get("yaw")
        pitch = euler_angles.get("pitch")
        roll = euler_angles.get("roll")

        yaw_excess = 0.0
        pitch_excess = 0.0
        roll_excess = 0.0

        if yaw is not None:
            yaw_excess = max(0.0, abs(yaw) - cfg["yaw_threshold_deg"])
        if pitch is not None:
            pitch_excess = max(0.0, abs(pitch) - cfg["pitch_threshold_deg"])
        if roll is not None:
            roll_excess = max(0.0, abs(roll) - cfg["roll_threshold_deg"])

        away_axes = sum(1 for v in [yaw_excess, pitch_excess, roll_excess] if v > 0)
        looking_away = away_axes >= 1

        # Confidence grows with normalized excess angle across axes
        # Normalize by thresholds to keep confidence in [0, 1]
        norm = 0.0
        denom = (
            (abs(yaw) if yaw is not None else 0.0)
            + (abs(pitch) if pitch is not None else 0.0)
            + (abs(roll) if roll is not None else 0.0)
            + 1e-6
        )
        norm = (yaw_excess + pitch_excess + roll_excess) / denom
        confidence = max(cfg["min_confidence"], min(1.0, norm)) if looking_away else 1.0 - min(1.0, norm)
        metrics.update(
            {
                "method": "euler",
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "yaw_excess": yaw_excess,
                "pitch_excess": pitch_excess,
                "roll_excess": roll_excess,
            }
        )

        return looking_away, float(confidence), metrics

    # 2) Landmark-only heuristic (very rough):
    # If both left and right eye corners are available, estimate horizontal gaze.
    # Expect landmark format as dict with keys x,y (normalized in [0,1]).
    if face_landmarks:
        # Indices below assume MediaPipe FaceMesh eye corner-like points.
        # We try multiple common indices and fallback if missing.
        candidate_indices = {
            "left_eye_outer": [33, 246],
            "right_eye_outer": [263, 463],
        }

        def pick_first_available(indices: List[int]) -> Optional[Dict]:
            for idx in indices:
                if 0 <= idx < len(face_landmarks):
                    lm = face_landmarks[idx]
                    if "x" in lm and "y" in lm:
                        return lm
            return None

        left_eye = pick_first_available(candidate_indices["left_eye_outer"])  # type: ignore[index]
        right_eye = pick_first_available(candidate_indices["right_eye_outer"])  # type: ignore[index]

        if left_eye and right_eye:
            # Horizontal eye line angle relative to image x-axis
            dx = right_eye["x"] - left_eye["x"]
            dy = right_eye["y"] - left_eye["y"]
            angle_deg = math.degrees(math.atan2(dy, dx))

            # If the eye line is strongly tilted (proxy for head roll/pose), mark away
            away = abs(angle_deg) > 25
            looking_away = away
            confidence = 0.6 if away else 0.4
            metrics.update({"method": "landmarks", "eye_line_angle_deg": angle_deg})
            return looking_away, float(confidence), metrics

    # Default fallback: cannot determine
    metrics.update({"method": "none"})
    return False, 0.0, metrics


def analyze_mouse_drift(
    samples: List[Dict],
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
    config: Optional[Dict] = None,
) -> Tuple[bool, float, Dict]:
    """
    Detect slow, continuous mouse cursor drifting.

    Heuristic:
    - Compute speed for consecutive points; consider time in seconds.
    - Drift if median speed is small but persistent, with low jerk, over >= window_secs.
    """

    cfg = {
        "window_secs": 10.0,
        "min_median_speed": 2.0,  # px/s
        "max_median_speed": 30.0,  # px/s
        "max_p90_speed": 60.0,  # px/s
        "min_total_path": 200.0,  # px
        "max_end_displacement": 50.0,  # px
    }
    if config:
        cfg.update(config)

    if len(samples) < 5:
        return False, 0.0, {"reason": "insufficient_samples"}

    # Sort by time
    pts = sorted(samples, key=lambda s: s["t"])  # type: ignore[index]
    t0 = pts[0]["t"]
    t1 = pts[-1]["t"]
    dur_s = max(0.0, (t1 - t0) / 1000.0)
    if dur_s < cfg["window_secs"]:
        return False, 0.0, {"reason": "insufficient_window", "duration_s": dur_s}

    # Compute per-step distances and speeds
    dists: List[float] = []
    speeds: List[float] = []
    total_path = 0.0
    for i in range(1, len(pts)):
        dx = float(pts[i]["x"]) - float(pts[i - 1]["x"])  # type: ignore[index]
        dy = float(pts[i]["y"]) - float(pts[i - 1]["y"])  # type: ignore[index]
        dt_ms = max(1.0, float(pts[i]["t"]) - float(pts[i - 1]["t"]))  # type: ignore[index]
        dist = math.hypot(dx, dy)
        speed = dist / (dt_ms / 1000.0)
        dists.append(dist)
        speeds.append(speed)
        total_path += dist

    # End-to-end displacement
    dx_end = float(pts[-1]["x"]) - float(pts[0]["x"])  # type: ignore[index]
    dy_end = float(pts[-1]["y"]) - float(pts[0]["y"])  # type: ignore[index]
    end_disp = math.hypot(dx_end, dy_end)

    def percentile(values: List[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
        return s[k]

    median_speed = percentile(speeds, 50.0)
    p90_speed = percentile(speeds, 90.0)

    is_drift = (
        cfg["min_median_speed"] <= median_speed <= cfg["max_median_speed"]
        and p90_speed <= cfg["max_p90_speed"]
        and total_path >= cfg["min_total_path"]
        and end_disp <= cfg["max_end_displacement"]
    )

    # Drift score blends normalized metrics
    score_parts = []
    # Median speed closeness to middle of band
    mid = 0.5 * (cfg["min_median_speed"] + cfg["max_median_speed"])  # type: ignore[operator]
    band = 0.5 * (cfg["max_median_speed"] - cfg["min_median_speed"]) + 1e-6  # type: ignore[operator]
    score_parts.append(max(0.0, 1.0 - abs(median_speed - mid) / band))
    # Low variability promotes drift
    score_parts.append(max(0.0, 1.0 - (p90_speed / (cfg["max_p90_speed"] + 1e-6))))
    # Path long, displacement short
    score_parts.append(min(1.0, total_path / (cfg["min_total_path"] + 1e-6)))
    score_parts.append(max(0.0, 1.0 - (end_disp / (cfg["max_end_displacement"] + 1e-6))))

    drift_score = sum(score_parts) / len(score_parts)

    metrics = {
        "duration_s": dur_s,
        "median_speed": median_speed,
        "p90_speed": p90_speed,
        "total_path": total_path,
        "end_displacement": end_disp,
        "screen_width": screen_width,
        "screen_height": screen_height,
    }

    return bool(is_drift), float(drift_score), metrics


