# Credits and third-party notices

MC3 Ultimate Music Tools is owned and maintained by **LowKey60Hz**. This attribution applies to original application code, the GUI, and project-specific integrations, not to third-party components or game/music content. It does not replace third-party licenses or assign a new license to their code.

> I just wanted to play MC3 with my own tunes :) — LowKey60Hz

## Bundled tools

WAV-to-RSM conversion uses the project's `ps_adpcm_encoder.py`, an independent Python implementation validated with the Retail menu probe. No separate encoder executable is bundled or required. The Edness attribution for the existing `rstm_build.py` ADS/SS2 container implementation is preserved; its WAV entry point has been modified for Python encoding.

The following scripts carry “Written by Edness” in their source headers. Credit: **Edness (EdnessP)**.

| File | Purpose | Local header version |
|---|---|---|
| `supporting_tools/dave.py` | Dave archive extraction and building | 1.5.3 |
| `supporting_tools/hash_build.py` | Hash/STREAMS archive extraction and building | 1.5 |
| `supporting_tools/rstm_build.py` | RSTM/RSM audio building | 1.4.2 |
| `supporting_tools/strtbl.py` | STRTBL string-table export and rebuilding | 1.3.4 |

The files above are under `supporting_tools` at the project root. Author-confirmed descriptions and source links: [Edness tools](https://ednessp.github.io/tools), [Edness scripts repository](https://github.com/EdnessP/scripts). Preserve the original author headers, including in other copies of these scripts. Local copies did not include a separate license text; attribution alone is not evidence of permission to redistribute or relicense them. Confirm applicable terms with the author before publishing distributions containing them.

## Installed runtime dependencies

The setup script installs these projects; they retain their own copyrights and license terms. They are not LowKey60Hz-authored code. Installed packages and native dependencies may carry additional third-party notices; preserve those when packaging an application.

| Component | Credits and upstream license information |
|---|---|
| Python | Python Software Foundation and contributors — [license](https://docs.python.org/3/license.html) |
| Qt / PySide6 | The Qt Company and contributors — [Qt for Python](https://doc.qt.io/qtforpython-6/), [licensing](https://doc.qt.io/qt-6/licensing.html); applicable open-source or commercial terms depend on the components/distribution |
| NumPy | NumPy contributors — [license](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| SciPy | SciPy contributors — [license](https://github.com/scipy/scipy/blob/main/LICENSE.txt) |
| python-soundfile | python-soundfile contributors — [project/license](https://github.com/bastibe/python-soundfile) |
| libsndfile | libsndfile contributors — [project/license](https://github.com/libsndfile/libsndfile) |
| python-sounddevice | python-sounddevice contributors — [project/license](https://github.com/spatialaudio/python-sounddevice) |
| PortAudio | PortAudio contributors — [license](https://www.portaudio.com/license.html) |

The links identify upstream projects; the license texts shipped with the exact versions being distributed govern those copies. This notice is not a replacement for required license texts or a completed redistribution-rights audit. No blanket project license is introduced by this file.

## Game and music

Midnight Club 3: DUB Edition Remix and related game content/trademarks belong to their respective rights holders. Music belongs to its respective rights holders. This is an independent community project, not affiliated with or endorsed by Rockstar Games, Take-Two Interactive, Sony, or the credited tool authors. Credits do not imply endorsement or transfer ownership.
