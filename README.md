# Sphere Light Director for ComfyUI

A visual lighting-reference node that generates two synchronized outputs:

- `lighting_reference` — a 1024 × 1024 sphere render showing light direction, color, strength, atmosphere, and shadow.
- `matching_prompt` — prompt text asking the image model to preserve that exact lighting condition.

The node is designed for directional-light workflows such as the
[Sun Direction LoRA for Flux 2 Klein 9B](https://huggingface.co/eric-venti-seeds/Sun-Direction-Lora-Flux2Klein9B),
but its IMAGE and STRING outputs can be used in any compatible ComfyUI graph.

## Controls

| Control | Range | Effect |
| --- | --- | --- |
| Rotation | −180° to 180° | Moves the light around the subject and changes the shadow direction. |
| Elevation | −18° to 90° | Moves through night, twilight, golden hour, daylight, and overhead sun. |
| Intensity | 0.2 to 3.0 | Changes direct-light strength. In Auto weather, very low daytime intensity becomes overcast. |
| Weather | Auto, Clear, Overcast | Lets the node infer the atmosphere or explicitly creates clear/overcast light. |
| Shadow softness | 0.0 to 1.0 | Moves from a crisp, hard-edged cast shadow to a broad soft shadow. |
| Shadow distance | 0.45 to 2.0 | Shortens or extends the cast shadow while elevation continues to influence its natural length. |

The preview color, mood label, reference image, and prompt all update from the same controls.

The sphere, camera, ground plane, and cast shadow are ray traced from one 3D coordinate system. Rotation can therefore send a shadow left, right, toward the camera, or away from it, but it can never place a ground shadow in the sky. A shadow appearing higher in the image means it travels away from the camera across the ground plane; a lower shadow travels toward the camera.

## Install

Copy or clone the `Sphere-Light-Render-ComfyUI` folder into ComfyUI's custom-node directory:

```text
ComfyUI/
└── custom_nodes/
    └── Sphere-Light-Render-ComfyUI/
        ├── __init__.py
        └── js/
            └── sphere_widget.js
```

Then restart ComfyUI and refresh the browser. No additional Python or JavaScript packages are required beyond ComfyUI's existing runtime.

Find the node at:

```text
Add Node → lighting → reference → ☀ Sphere Light Director
```

## Suggested graph

1. Connect `lighting_reference` to the image/reference input used by the lighting LoRA or image-conditioning workflow.
2. Connect `matching_prompt` to the FLUX text-encode node. It includes the LoRA's exact trigger phrase and identifies the photographic scene as content and the sphere as the lighting guide.
3. Adjust the sphere until its highlight and cast shadow match the intended shot.

For the published Sun Direction LoRA workflow, use an overcast or directionally neutral scene image as the content reference and the node output as the sphere reference. The generated prompt is intentionally a single direct editing instruction for FLUX.2 Klein 9B.

## Sun Direction LoRA v1 limitation

The published v1 LoRA is trained primarily for exterior sun direction. Its author recommends first converting the scene to overcast or otherwise removing its existing directional light. Night mood, light color, intensity, hardness, and distance are useful controls for general FLUX.2 multi-reference editing, but v1 was not trained to reproduce all of them reliably. Production-reliable control of those attributes requires a LoRA trained with labeled variations for each attribute.

The backend generates the image directly from the numeric settings, so the node also works when a workflow is submitted through ComfyUI API mode.
