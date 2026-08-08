import { app } from "../../scripts/app.js";

const EXTENSION_NAME = "SphereLightDirector.VisualWidget";
const CLASS_NAME = "SphereLightNode";

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const mix = (a, b, t) => a.map((value, index) => value * (1 - t) + b[index] * t);
const rgb = (color, alpha = 1) =>
  `rgba(${color.map((value) => Math.round(clamp(value, 0, 1) * 255)).join(",")},${alpha})`;

function profileFor(rotation, elevation, intensity, weather, shadowSoftness = 0.35) {
  const overcast = weather === "Overcast" || (weather === "Auto" && intensity <= 0.65 && elevation > 5);
  let phase;
  let mood;
  let light;
  let top;
  let bottom;
  let ambient;
  let softness;

  if (elevation <= -6) {
    phase = "NIGHT";
    mood = "Moonlit night";
    light = [0.36, 0.48, 0.82];
    top = [0.025, 0.035, 0.075];
    bottom = [0.085, 0.105, 0.17];
    ambient = [0.075, 0.09, 0.15];
    softness = 0.66;
  } else if (elevation < 6) {
    const t = (elevation + 6) / 12;
    phase = "TWILIGHT";
    mood = rotation < 0 ? "Blue-hour dawn" : "Blue-hour dusk";
    light = mix([0.48, 0.58, 0.92], [1, 0.43, 0.2], t);
    top = mix([0.055, 0.075, 0.15], [0.21, 0.24, 0.38], t);
    bottom = mix([0.16, 0.17, 0.28], [0.62, 0.31, 0.21], t);
    ambient = mix([0.09, 0.11, 0.19], [0.21, 0.17, 0.16], t);
    softness = 0.52;
  } else if (elevation < 18) {
    const t = (elevation - 6) / 12;
    phase = "GOLDEN HOUR";
    mood = rotation < 0 ? "Warm sunrise" : "Warm sunset";
    light = mix([1, 0.39, 0.13], [1, 0.72, 0.4], t);
    top = mix([0.26, 0.34, 0.5], [0.34, 0.49, 0.66], t);
    bottom = mix([0.74, 0.37, 0.2], [0.68, 0.56, 0.43], t);
    ambient = mix([0.2, 0.15, 0.12], [0.24, 0.23, 0.2], t);
    softness = 0.34;
  } else {
    const t = clamp((elevation - 18) / 55, 0, 1);
    phase = "DAYLIGHT";
    mood = "Clear daylight";
    light = mix([1, 0.78, 0.53], [0.96, 0.98, 1], t);
    top = mix([0.34, 0.53, 0.72], [0.25, 0.48, 0.72], t);
    bottom = mix([0.72, 0.69, 0.61], [0.66, 0.72, 0.75], t);
    ambient = mix([0.25, 0.24, 0.21], [0.28, 0.3, 0.32], t);
    softness = 0.24;
  }

  if (overcast) {
    mood = `Overcast ${phase.toLowerCase()}`;
    light = mix(light, [0.72, 0.79, 0.86], 0.72);
    top = mix(top, [0.28, 0.33, 0.38], 0.72);
    bottom = mix(bottom, [0.47, 0.49, 0.5], 0.75);
    ambient = mix(ambient, [0.31, 0.33, 0.35], 0.68);
  }
  softness = clamp(Number(shadowSoftness), 0, 1);
  return { phase, mood, light, top, bottom, ambient, softness, overcast };
}

function renderPreview(
  canvas,
  rotation,
  elevation,
  intensity,
  weather,
  shadowSoftness,
  shadowDistance,
) {
  const width = canvas.width;
  const height = canvas.height;
  const ctx = canvas.getContext("2d");
  const profile = profileFor(rotation, elevation, intensity, weather, shadowSoftness);
  const az = (rotation * Math.PI) / 180;
  const el = (Math.max(elevation, 4) * Math.PI) / 180;
  const lx = Math.cos(el) * Math.sin(az);
  const ly = Math.sin(el);
  const lz = Math.cos(el) * Math.cos(az);
  const projectionElevation = Math.atan(
    Math.tan(el) / clamp(Number(shadowDistance), 0.45, 2),
  );
  const slx = Math.cos(projectionElevation) * Math.sin(az);
  const sly = Math.sin(projectionElevation);
  const slz = Math.cos(projectionElevation) * Math.cos(az);
  const smoothstep = (edge0, edge1, value) => {
    const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return t * t * (3 - 2 * t);
  };
  const gamma = (value) => Math.pow(clamp(value, 0, 1), 1 / 2.2);

  // Same perspective scene as the backend: unit sphere at the origin, ground at
  // y=-1, camera at (0, 3.8, 6.5). Every shadow pixel is a real plane hit.
  const cameraY = 3.8;
  const cameraZ = 6.5;
  const forwardY = -0.53351;
  const forwardZ = -0.84579;
  const upY = 0.84579;
  const upZ = -0.53351;
  const tanHalfFov = Math.tan((35 * Math.PI) / 360);
  const sphereC = cameraY * cameraY + cameraZ * cameraZ - 1;
  const groundBase = mix(profile.bottom, [0.36, 0.36, 0.34], 0.58);
  const groundColor = groundBase.map((value, channel) =>
    value * clamp(
      0.42 + profile.light[channel] * ly * clamp(Number(intensity), 0.2, 3) * 0.34,
      0,
      1,
    ),
  );
  const base = [0.76, 0.75, 0.71];
  const ambientLevel = 0.11 +
    ((profile.ambient[0] + profile.ambient[1] + profile.ambient[2]) / 3) *
      (0.52 + profile.softness * 0.32);
  const directGain = clamp(Number(intensity), 0.2, 3) * (profile.overcast ? 0.7 : 0.96);
  const image = ctx.createImageData(width, height);
  const pixels = image.data;

  for (let py = 0; py < height; py += 1) {
    const screenY = (1 - (2 * (py + 0.5)) / height) * tanHalfFov;
    for (let px = 0; px < width; px += 1) {
      const screenX = ((2 * (px + 0.5)) / width - 1) * tanHalfFov;
      let dx = screenX;
      let dy = forwardY + screenY * upY;
      let dz = forwardZ + screenY * upZ;
      const rayLength = Math.hypot(dx, dy, dz);
      dx /= rayLength;
      dy /= rayLength;
      dz /= rayLength;

      const sphereB = dy * cameraY + dz * cameraZ;
      const discriminant = sphereB * sphereB - sphereC;
      let sphereT = Number.POSITIVE_INFINITY;
      if (discriminant >= 0) {
        const candidate = -sphereB - Math.sqrt(discriminant);
        if (candidate > 0) sphereT = candidate;
      }
      const planeT = dy < -1e-6 ? (-1 - cameraY) / dy : Number.POSITIVE_INFINITY;
      const hitSphere = sphereT < planeT;
      let color;

      if (hitSphere) {
        const nx = dx * sphereT;
        const ny = cameraY + dy * sphereT;
        const nz = cameraZ + dz * sphereT;
        const diffuse = Math.max(0, nx * lx + ny * ly + nz * lz);
        const wrap = 0.025 + profile.softness * 0.22;
        const shaped = Math.pow(
          clamp((diffuse + wrap) / (1 + wrap), 0, 1),
          1.22 - profile.softness * 0.4,
        );
        const rim = Math.pow(clamp(1 + nx * dx + ny * dy + nz * dz, 0, 1), 3);
        color = base.map((value, channel) => {
          let linear = value * ambientLevel +
            value * profile.light[channel] * shaped * directGain +
            rim * profile.top[channel] * 0.1;
          linear /= 1 + Math.max(linear - 0.72, 0) * 0.48;
          return gamma(linear);
        });
      } else if (Number.isFinite(planeT) && planeT > 0) {
        const worldX = dx * planeT;
        const worldY = -1;
        const worldZ = cameraZ + dz * planeT;
        const toX = -worldX;
        const toY = -worldY;
        const toZ = -worldZ;
        const closestT = toX * slx + toY * sly + toZ * slz;
        const closestX = worldX + closestT * slx;
        const closestY = worldY + closestT * sly;
        const closestZ = worldZ + closestT * slz;
        const axisDistance = Math.hypot(closestX, closestY, closestZ);
        const penumbra = 0.012 + profile.softness *
          (0.1 + 0.025 * clamp(closestT, 0, 12));
        const shadow = closestT > 0
          ? 1 - smoothstep(1 - penumbra, 1 + penumbra, axisDistance)
          : 0;
        const shadowStrength = (0.72 - profile.softness * 0.16) *
          clamp(Number(intensity) / 1.5, 0.55, 1.2);
        color = groundColor.map((value) => gamma(value * (1 - shadow * shadowStrength)));
      } else {
        const skyAmount = smoothstep(0, height, py);
        color = mix(profile.top, profile.bottom, skyAmount).map(gamma);
      }

      const index = (py * width + px) * 4;
      pixels[index] = color[0] * 255;
      pixels[index + 1] = color[1] * 255;
      pixels[index + 2] = color[2] * 255;
      pixels[index + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return profile;
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, radius);
}

app.registerExtension({
  name: EXTENSION_NAME,

  async nodeCreated(node) {
    if (node.comfyClass !== CLASS_NAME) return;

    node.color = "#272820";
    node.bgcolor = "#171915";
    node.shape = LiteGraph.ROUND_SHAPE;

    const canvas = document.createElement("canvas");
    canvas.width = 360;
    canvas.height = 360;
    node._sphereLightCanvas = canvas;
    node._sphereLightProfile = null;

    const widgetValue = (name, fallback) => {
      const widget = node.widgets?.find((item) => item.name === name);
      return widget ? widget.value : fallback;
    };

    let renderTimer = null;
    const update = () => {
      node._sphereLightProfile = renderPreview(
        canvas,
        Number(widgetValue("rotation", 0)),
        Number(widgetValue("elevation", 35)),
        Number(widgetValue("intensity", 1.5)),
        String(widgetValue("weather", "Auto")),
        Number(widgetValue("shadow_softness", 0.35)),
        Number(widgetValue("shadow_distance", 1.0)),
      );
      app.graph.setDirtyCanvas(true, false);
    };
    const scheduleUpdate = () => {
      clearTimeout(renderTimer);
      renderTimer = setTimeout(update, 45);
    };

    const visualWidget = {
      name: "_lighting_instrument",
      type: "sphere_light_instrument",
      value: null,
      serialize: false,
      options: { serialize: false },

      computeSize(width) {
        const panelWidth = Math.max(width - 24, 120);
        const imageHeight = panelWidth * (canvas.height / canvas.width);
        return [width, imageHeight + 52];
      },

      draw(ctx, owner, width, y, height) {
        if (!owner._sphereLightProfile) return;
        const x = 12;
        const panelWidth = width - 24;
        // Never use LiteGraph's transient draw height here: it can be a default row
        // height while resizing. Deriving both dimensions from the source canvas
        // guarantees that the sphere remains circular at every node width.
        const imageHeight = panelWidth * (canvas.height / canvas.width);
        const profile = owner._sphereLightProfile;

        ctx.save();
        roundedRect(ctx, x, y + 4, panelWidth, imageHeight, 12);
        ctx.clip();
        ctx.drawImage(owner._sphereLightCanvas, x, y + 4, panelWidth, imageHeight);

        const veil = ctx.createLinearGradient(0, y + 4, 0, y + 66);
        veil.addColorStop(0, "rgba(10, 12, 10, 0.66)");
        veil.addColorStop(1, "rgba(10, 12, 10, 0)");
        ctx.fillStyle = veil;
        ctx.fillRect(x, y + 4, panelWidth, 66);
        ctx.restore();

        ctx.save();
        ctx.font = "600 10px sans-serif";
        ctx.textBaseline = "middle";
        const chipText = profile.overcast ? "OVERCAST" : profile.phase;
        const chipWidth = Math.max(70, ctx.measureText(chipText).width + 22);
        ctx.fillStyle = "rgba(20, 22, 18, 0.76)";
        roundedRect(ctx, x + 12, y + 16, chipWidth, 24, 12);
        ctx.fill();
        ctx.fillStyle = rgb(profile.light);
        ctx.beginPath();
        ctx.arc(x + 24, y + 28, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#f1f0e8";
        ctx.fillText(chipText, x + 33, y + 28);

        ctx.font = "600 13px sans-serif";
        ctx.fillStyle = "#efeee6";
        ctx.fillText(profile.mood, x, y + imageHeight + 25);
        ctx.font = "10px sans-serif";
        ctx.fillStyle = "#9c9e91";
        ctx.textAlign = "right";
        ctx.fillText("IMAGE + MATCHING PROMPT", x + panelWidth, y + imageHeight + 25);
        ctx.restore();
      },
    };

    if (node.addCustomWidget) node.addCustomWidget(visualWidget);
    else node.widgets.push(visualWidget);

    const hookWidgets = () => {
      for (const name of [
        "rotation",
        "elevation",
        "intensity",
        "weather",
        "shadow_softness",
        "shadow_distance",
      ]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget || widget._sphereLightHooked) continue;
        widget._sphereLightHooked = true;
        const original = widget.callback;
        widget.callback = function callback(value, ...args) {
          original?.call(this, value, ...args);
          scheduleUpdate();
        };
      }
    };

    const originalRemoved = node.onRemoved;
    node.onRemoved = function onRemoved(...args) {
      originalRemoved?.apply(this, args);
      clearTimeout(renderTimer);
      this._sphereLightCanvas = null;
      this._sphereLightProfile = null;
    };

    setTimeout(() => {
      hookWidgets();
      update();
      const width = Math.max(node.size?.[0] || 360, 340);
      const computed = node.computeSize?.() || [width, 440];
      node.setSize([width, Math.max(computed[1], 440)]);
    }, 80);

    setTimeout(hookWidgets, 600);
  },
});
