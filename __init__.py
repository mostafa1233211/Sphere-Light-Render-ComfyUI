"""Cinematic sphere-light direction reference node for ComfyUI."""

import math

import numpy as np
import torch


def _smoothstep(edge0, edge1, value):
    """Vector-friendly smoothstep with safe handling of equal edges."""
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _mix(a, b, amount):
    return np.asarray(a, dtype=np.float32) * (1.0 - amount) + np.asarray(
        b, dtype=np.float32
    ) * amount


def _lighting_profile(rotation, elevation, intensity, weather, shadow_softness=0.35):
    """Return a single source of truth for color, mood, softness and copy."""
    rotation = float(rotation)
    elevation = float(elevation)
    intensity = float(intensity)
    weather_key = str(weather).lower()

    if weather_key == "auto":
        is_overcast = intensity <= 0.65 and elevation > 5.0
    else:
        is_overcast = weather_key == "overcast"

    if elevation <= -6.0:
        phase = "night"
        mood = "moonlit night"
        light_color = np.array([0.36, 0.48, 0.82], dtype=np.float32)
        sky_top = np.array([0.025, 0.035, 0.075], dtype=np.float32)
        sky_bottom = np.array([0.085, 0.105, 0.17], dtype=np.float32)
        ambient = np.array([0.075, 0.09, 0.15], dtype=np.float32)
    elif elevation < 6.0:
        phase = "twilight"
        mood = "blue-hour dawn" if rotation < 0 else "blue-hour dusk"
        amount = (elevation + 6.0) / 12.0
        light_color = _mix([0.48, 0.58, 0.92], [1.0, 0.43, 0.20], amount)
        sky_top = _mix([0.055, 0.075, 0.15], [0.21, 0.24, 0.38], amount)
        sky_bottom = _mix([0.16, 0.17, 0.28], [0.62, 0.31, 0.21], amount)
        ambient = _mix([0.09, 0.11, 0.19], [0.21, 0.17, 0.16], amount)
    elif elevation < 18.0:
        phase = "golden hour"
        mood = "warm sunrise" if rotation < 0 else "warm sunset"
        amount = (elevation - 6.0) / 12.0
        light_color = _mix([1.0, 0.39, 0.13], [1.0, 0.72, 0.40], amount)
        sky_top = _mix([0.26, 0.34, 0.50], [0.34, 0.49, 0.66], amount)
        sky_bottom = _mix([0.74, 0.37, 0.20], [0.68, 0.56, 0.43], amount)
        ambient = _mix([0.20, 0.15, 0.12], [0.24, 0.23, 0.20], amount)
    else:
        phase = "daylight"
        mood = "clear daylight"
        amount = np.clip((elevation - 18.0) / 55.0, 0.0, 1.0)
        light_color = _mix([1.0, 0.78, 0.53], [0.96, 0.98, 1.0], amount)
        sky_top = _mix([0.34, 0.53, 0.72], [0.25, 0.48, 0.72], amount)
        sky_bottom = _mix([0.72, 0.69, 0.61], [0.66, 0.72, 0.75], amount)
        ambient = _mix([0.25, 0.24, 0.21], [0.28, 0.30, 0.32], amount)

    if is_overcast:
        mood = f"overcast {phase}"
        light_color = _mix(light_color, [0.72, 0.79, 0.86], 0.72)
        sky_top = _mix(sky_top, [0.28, 0.33, 0.38], 0.72)
        sky_bottom = _mix(sky_bottom, [0.47, 0.49, 0.50], 0.75)
        ambient = _mix(ambient, [0.31, 0.33, 0.35], 0.68)

    # Shadow character is intentionally independent from time of day. This gives
    # the reference enough contrast to teach a model hard, soft and overcast looks.
    softness = float(np.clip(shadow_softness, 0.0, 1.0))

    return {
        "phase": phase,
        "mood": mood,
        "light_color": light_color,
        "sky_top": sky_top,
        "sky_bottom": sky_bottom,
        "ambient": ambient,
        "softness": softness,
        "overcast": is_overcast,
    }


def _direction_words(rotation, elevation):
    az = math.radians(rotation)
    screen_x = math.sin(az)
    depth = math.cos(az)

    if screen_x < -0.28:
        side = "camera-left"
    elif screen_x > 0.28:
        side = "camera-right"
    else:
        side = "centered"

    if depth > 0.35:
        depth_words = "from the camera side"
    elif depth < -0.35:
        depth_words = "from behind the subject"
    else:
        depth_words = "across the subject"

    if elevation < 6:
        height = "near the horizon"
    elif elevation < 25:
        height = "at a low angle"
    elif elevation < 60:
        height = "at a medium-high angle"
    else:
        height = "from high overhead"
    return f"{side}, {depth_words}, {height}"


def build_prompt(
    rotation, elevation, intensity, weather, shadow_softness, shadow_distance
):
    profile = _lighting_profile(
        rotation, elevation, intensity, weather, shadow_softness
    )
    softness = (
        "very soft, broad shadows"
        if profile["softness"] > 0.72
        else "soft-edged shadows"
        if profile["softness"] > 0.45
        else "defined directional shadows"
    )
    strength = (
        "subtle" if intensity < 0.8 else "strong" if intensity > 2.1 else "balanced"
    )
    reach = (
        "short, close shadows"
        if shadow_distance < 0.8
        else "long, far-reaching shadows"
        if shadow_distance > 1.25
        else "medium-length shadows"
    )
    direction = _direction_words(rotation, elevation)
    return (
        "Match the sun direction from the reference. The photographic scene image is the "
        "content to relight; the sphere image is the lighting guide. Keep the scene's "
        "subjects, identity, geometry, materials, camera, composition, and details unchanged. "
        f"Apply {profile['mood']} illumination from {direction}, with {strength} intensity, "
        f"{softness}, and {reach}. Match the sphere's highlight side, shaded side, cast-shadow "
        "direction, shadow reach, color temperature, ambient fill, and contrast."
    )


def render_sphere(
    rotation,
    elevation,
    intensity,
    weather,
    shadow_softness=0.35,
    shadow_distance=1.0,
    size=1024,
):
    """Ray trace a sphere and its physically projected shadow onto a ground plane."""
    profile = _lighting_profile(
        rotation, elevation, intensity, weather, shadow_softness
    )
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = xx / max(size - 1, 1)
    v = yy / max(size - 1, 1)

    # Perspective camera. Rays determine both the true horizon and all visible
    # ground-plane pixels, so a cast shadow can never leak into the sky.
    camera = np.array([0.0, 3.8, 6.5], dtype=np.float32)
    target = np.array([0.0, -0.30, 0.0], dtype=np.float32)
    forward = target - camera
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0], dtype=np.float32))
    right /= np.linalg.norm(right)
    camera_up = np.cross(right, forward)
    tan_half_fov = math.tan(math.radians(35.0) * 0.5)
    screen_x = (2.0 * u - 1.0) * tan_half_fov
    screen_y = (1.0 - 2.0 * v) * tan_half_fov
    rays = (
        forward[None, None, :]
        + screen_x[..., None] * right[None, None, :]
        + screen_y[..., None] * camera_up[None, None, :]
    )
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)

    # Start with atmosphere; ground and sphere replace only their actual ray hits.
    sky_mix = _smoothstep(0.0, 0.92, v)[..., None]
    image = profile["sky_top"] * (1.0 - sky_mix) + profile["sky_bottom"] * sky_mix

    # Analytic intersections with a unit sphere at the origin and y=-1 plane.
    sphere_b = np.sum(rays * camera[None, None, :], axis=2)
    sphere_c = float(np.dot(camera, camera) - 1.0)
    discriminant = sphere_b * sphere_b - sphere_c
    sphere_t = np.where(
        discriminant >= 0.0,
        -sphere_b - np.sqrt(np.clip(discriminant, 0.0, None)),
        np.inf,
    )
    sphere_t = np.where(sphere_t > 0.0, sphere_t, np.inf)
    plane_t = (-1.0 - camera[1]) / np.where(
        np.abs(rays[..., 1]) > 1e-6, rays[..., 1], -1e-6
    )
    plane_t = np.where((rays[..., 1] < 0.0) & (plane_t > 0.0), plane_t, np.inf)
    sphere_mask = sphere_t < plane_t
    plane_mask = np.isfinite(plane_t) & ~sphere_mask

    # The visible light direction is always above the ground. Negative elevation
    # selects night/twilight color, while a low moon angle remains physically valid.
    azimuth = math.radians(float(rotation))
    light_elevation = math.radians(max(float(elevation), 4.0))
    light = np.array(
        [
            math.cos(light_elevation) * math.sin(azimuth),
            math.sin(light_elevation),
            math.cos(light_elevation) * math.cos(azimuth),
        ],
        dtype=np.float32,
    )

    # Shade the plane, then analytically test its rays toward the light against the
    # sphere. shadow_distance changes the effective projection elevation without
    # breaking the relation between azimuth, sphere highlight and shadow direction.
    safe_plane_t = np.where(np.isfinite(plane_t), plane_t, 0.0)
    plane_points = camera[None, None, :] + rays * safe_plane_t[..., None]
    ground_base = _mix(profile["sky_bottom"], [0.36, 0.36, 0.34], 0.58)
    ground_light = np.clip(
        0.42
        + profile["light_color"]
        * light[1]
        * np.clip(float(intensity), 0.2, 3.0)
        * 0.34,
        0.0,
        1.0,
    )
    ground_rgb = ground_base * ground_light

    projection_elevation = math.atan(
        math.tan(light_elevation) / float(np.clip(shadow_distance, 0.45, 2.0))
    )
    shadow_light = np.array(
        [
            math.cos(projection_elevation) * math.sin(azimuth),
            math.sin(projection_elevation),
            math.cos(projection_elevation) * math.cos(azimuth),
        ],
        dtype=np.float32,
    )
    to_center = -plane_points
    closest_t = np.sum(to_center * shadow_light[None, None, :], axis=2)
    closest = plane_points + closest_t[..., None] * shadow_light[None, None, :]
    axis_distance = np.linalg.norm(closest, axis=2)
    penumbra = 0.012 + profile["softness"] * (
        0.10 + 0.025 * np.clip(closest_t, 0.0, 12.0)
    )
    shadow = 1.0 - _smoothstep(1.0 - penumbra, 1.0 + penumbra, axis_distance)
    shadow *= (closest_t > 0.0) * plane_mask
    shadow_strength = (0.72 - profile["softness"] * 0.16) * np.clip(
        float(intensity) / 1.5, 0.55, 1.2
    )
    shaded_ground = ground_rgb[None, None, :] * (
        1.0 - shadow[..., None] * shadow_strength
    )
    image = np.where(plane_mask[..., None], shaded_ground, image)

    # Sphere lighting uses the same azimuth as the cast shadow.
    safe_sphere_t = np.where(np.isfinite(sphere_t), sphere_t, 0.0)
    sphere_points = camera[None, None, :] + rays * safe_sphere_t[..., None]
    normals = sphere_points / np.maximum(
        np.linalg.norm(sphere_points, axis=2, keepdims=True), 1e-6
    )
    diffuse = np.clip(np.sum(normals * light[None, None, :], axis=2), 0.0, 1.0)
    wrap = 0.025 + profile["softness"] * 0.22
    shaped_light = np.power(
        np.clip((diffuse + wrap) / (1.0 + wrap), 0.0, 1.0),
        1.22 - profile["softness"] * 0.40,
    )
    base = np.array([0.76, 0.75, 0.71], dtype=np.float32)
    ambient_level = 0.11 + float(np.mean(profile["ambient"])) * (
        0.52 + profile["softness"] * 0.32
    )
    direct_gain = np.clip(float(intensity), 0.2, 3.0) * (
        0.70 if profile["overcast"] else 0.96
    )
    sphere_rgb = (
        base[None, None, :] * ambient_level
        + base[None, None, :]
        * profile["light_color"][None, None, :]
        * shaped_light[..., None]
        * direct_gain
    )
    rim = np.power(
        np.clip(1.0 + np.sum(normals * rays, axis=2), 0.0, 1.0), 3.0
    )
    sphere_rgb += rim[..., None] * profile["sky_top"][None, None, :] * 0.10
    sphere_rgb = sphere_rgb / (
        1.0 + np.maximum(sphere_rgb - 0.72, 0.0) * 0.48
    )
    image = np.where(sphere_mask[..., None], sphere_rgb, image)

    vignette = 1.0 - 0.12 * np.clip(
        ((u - 0.5) ** 2 + (v - 0.48) ** 2) / 0.5, 0.0, 1.0
    )
    image *= vignette[..., None]
    image = np.power(np.clip(image, 0.0, 1.0), 1.0 / 2.2)
    return image.astype(np.float32)


class SphereLightNode:
    """Generate a lighting reference image and a matching natural-language prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "rotation": (
                    "FLOAT",
                    {"default": 0.0, "min": -180.0, "max": 180.0, "step": 1.0, "display": "slider"},
                ),
                "elevation": (
                    "FLOAT",
                    {"default": 35.0, "min": -18.0, "max": 90.0, "step": 1.0, "display": "slider"},
                ),
                "intensity": (
                    "FLOAT",
                    {"default": 1.5, "min": 0.2, "max": 3.0, "step": 0.1, "display": "slider"},
                ),
                "weather": (["Auto", "Clear", "Overcast"], {"default": "Auto"}),
                "shadow_softness": (
                    "FLOAT",
                    {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05, "display": "slider"},
                ),
                "shadow_distance": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.45, "max": 2.0, "step": 0.05, "display": "slider"},
                ),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("lighting_reference", "matching_prompt")
    FUNCTION = "execute"
    CATEGORY = "lighting/reference"
    DESCRIPTION = (
        "Creates a sphere light-direction reference and a prompt that describes the exact "
        "same direction, mood, color temperature, and shadow character."
    )
    OUTPUT_NODE = False

    def execute(
        self,
        rotation,
        elevation,
        intensity,
        weather,
        shadow_softness,
        shadow_distance,
    ):
        image = render_sphere(
            rotation,
            elevation,
            intensity,
            weather,
            shadow_softness,
            shadow_distance,
        )
        tensor = torch.from_numpy(image).unsqueeze(0)
        prompt = build_prompt(
            rotation,
            elevation,
            intensity,
            weather,
            shadow_softness,
            shadow_distance,
        )
        return (tensor, prompt)


NODE_CLASS_MAPPINGS = {"SphereLightNode": SphereLightNode}
NODE_DISPLAY_NAME_MAPPINGS = {"SphereLightNode": "☀ Sphere Light Director"}
WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
