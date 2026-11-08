# Character artwork

The artwork in `assets/expressions/` (six WebP sprites and `preview.png`) is a matched six-expression chibi whale-maid series,
selected without pixel edits from [keleus/deepseek-pet](https://github.com/keleus/deepseek-pet)
at commit `b9b61a35c3b2443ecdeab0ed442d6b33c603d343`.
The original filenames are recorded in `assets/expressions/sources.json`.
The preview arranges the six sprites on a background. Runtime circular backing, contact shadows, mood rings and transparent character compositing are modifications rendered into a local cache.

These images are **not covered by this project's MIT license**. The character
artwork is reused under **CC BY-NC-SA 4.0**, retaining the upstream attribution
chain documented by [AIR-pixel's asset notice](https://github.com/AIR-pixel/deepseek-whale-maid-pet/blob/main/LICENSE-ASSETS):

- Original character “溟月”: 上善无形, 2025.06. [Author](https://space.bilibili.com/4456176).
- Maid outfit and DeepSeek redesign: ZipZipPipe, 2026.04. [Author](https://space.bilibili.com/4168597).
- Desktop-pet sprite assets: [keleus/deepseek-pet](https://github.com/keleus/deepseek-pet).
- Upstream desktop-pet program and asset reprocessing: air / AIR-pixel, 2026.09.
- This project: six-state selection and runtime character-over-circle compositing; no authorship claim over the source art.

[CC BY-NC-SA 4.0 license](https://creativecommons.org/licenses/by-nc-sa/4.0/)
requires attribution, non-commercial use and sharing adaptations under the same
license. Code may be reused under MIT; these bundled images require separate
compliance with their asset license. Replace them with your own licensed art
for uses outside that grant.

This is an unofficial fan project, with no affiliation with or endorsement by
DeepSeek or the artists. Names and marks remain with their owners.

# Model and reference audio

No model weights, voice reference recordings, personal portrait or derived
personal expression images are distributed in this repository.

The optional model is
[mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16),
converted from Qwen/Qwen3-TTS-12Hz-1.7B-Base and published under Apache-2.0.
Users download it separately and provide their own permitted voice reference.
