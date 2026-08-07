---
name: bbh-image
description: Query BBH image models and account points, upload temporary reference images, submit image-generation jobs, poll task status, and return generated image URLs through the bundled CLI. Use when Codex needs to generate images with BBH OpenAPI, inspect BBH model capabilities, check BBH credits, or manage BBH image tasks from a terminal.
---

# BBH Image

Use the bundled CLI for every BBH OpenAPI operation. Keep API keys out of prompts, logs, files, and command history whenever possible.

## Setup

Resolve this skill's directory and invoke:

```bash
python3 <skill-dir>/scripts/bbh_image.py --help
```

Require `BBH_API_KEY` in the environment. If it is missing, ask the user to set it in their shell and retry; do not ask them to paste it into the conversation.

Optional environment variables:

- `BBH_BASE_URL`: defaults to `https://bbh-ai-server.benbh.cn`
- `BBH_REQUEST_TIMEOUT`: per-request timeout in seconds; defaults to `30`

## Workflow

1. Run `models` when the model ID, supported parameters, tier, image limits, or pricing are unknown.
2. Run `points` before a costly generation when the user wants a balance check or insufficient credits are possible.
3. Choose `generate` for a single task that should be submitted and awaited.
4. Choose `submit`, followed by `wait`, for queues or parallel task management.
5. Use `--image-file` for an inline Base64 reference image. Use `upload` and then `--image-url` when a temporary URL is preferable.
6. Return the `task_id`, final status, and generated image URLs. Mention API errors concisely and preserve the server message.

## Commands

```bash
# Discover models
python3 <skill-dir>/scripts/bbh_image.py models --task-type txt2img

# Check points
python3 <skill-dir>/scripts/bbh_image.py points

# Generate and wait
python3 <skill-dir>/scripts/bbh_image.py generate \
  --model-id 101 \
  --prompt "a cinematic paper-cut city at sunrise" \
  --aspect-ratio 16:9 \
  --image-size 1K

# Submit now, wait later
python3 <skill-dir>/scripts/bbh_image.py submit --model-id 101 --prompt "a red panda astronaut"
python3 <skill-dir>/scripts/bbh_image.py wait <task-id>

# Reference images
python3 <skill-dir>/scripts/bbh_image.py generate \
  --model-id 101 \
  --prompt "turn this into watercolor" \
  --image-file ./reference.png
```

Use repeatable `--param KEY=VALUE` for model-specific top-level parameters and `--user-param KEY=VALUE` for `user_params`. Values that are valid JSON are decoded; other values remain strings.

Read [references/api.md](references/api.md) when raw endpoint details, payload fields, response handling, or exit codes are needed.
