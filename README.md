# benbh-skills

Open-source Codex skills from BenBH.

## Available skills

### `bbh-image`

Generate images through the BBH OpenAPI from Codex or a terminal. It includes a dependency-free Python CLI for model discovery, point lookup, temporary uploads, task submission, polling, and result extraction.

## Install

In Codex, invoke `$skill-installer` and ask it to install:

```text
https://github.com/theday-seeyou/benbh-skills/tree/main/skills/bbh-image
```

Or install manually:

```bash
git clone git@github.com:theday-seeyou/benbh-skills.git
mkdir -p ~/.codex/skills
cp -R benbh-skills/skills/bbh-image ~/.codex/skills/bbh-image
```

Restart Codex after installing a skill.

## Configure BBH Image

Set the API key in the environment that launches Codex:

```bash
export BBH_API_KEY="your-api-key"
```

Optional settings:

```bash
export BBH_BASE_URL="https://bbh-ai-server.benbh.cn"
export BBH_REQUEST_TIMEOUT="30"
```

Do not commit API keys or paste them into prompts.

## CLI examples

```bash
python3 skills/bbh-image/scripts/bbh_image.py models
python3 skills/bbh-image/scripts/bbh_image.py points
python3 skills/bbh-image/scripts/bbh_image.py generate \
  --model-id 101 \
  --prompt "a cute cat" \
  --aspect-ratio 1:1 \
  --image-size 1K
```

Run `python3 skills/bbh-image/scripts/bbh_image.py --help` for all commands.

## License

[MIT](LICENSE)
