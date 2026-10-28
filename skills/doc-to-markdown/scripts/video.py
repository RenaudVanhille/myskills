# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = ["av>=12", "faster-whisper>=1.1,<2", "numpy>=1.24", "pillow>=10"]
# ///
"""Convertit une vidéo (démo applicative...) ou un enregistrement audio en Markdown, en local.

Rien ne sort de la machine : le réseau du processus est coupé avant tout
travail (model_store.forbid_network), la vidéo est lue par PyAV (FFmpeg
embarqué), la parole transcrite par faster-whisper avec un modèle du cache
local, téléchargé avant depuis une source épinglée de model-sources.json
(`doctor.py video --prefetch`, skill check-prerequisites). Jamais
ModelScope, jamais un service de transcription en ligne.

Les images clés (changement d'écran) sont extraites dans
<sortie>/attachments/<nom>-NN.png et listées dans `vision_pages` : la vision
du modèle du harness les décrit ensuite. La transcription est rangée sous
l'image affichée pendant qu'elle est dite.

Usage :
    uv run scripts/video.py FICHIER [...] [--out DOSSIER] [--language fr] [--model whisper-small]
        [--no-audio] [--interval 1.0] [--threshold 0.06] [--max-frames 40]

Sans modèle dans le cache, les images clés sont tout de même extraites et un
avertissement dit comment obtenir le modèle.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import model_store  # noqa: E402

model_store.forbid_network()

from script_report import print_report  # noqa: E402
from validate import check  # noqa: E402

VIDEO = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv"}
AUDIO = {".m4a", ".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma"}
MEDIA = VIDEO | AUDIO
# Côté le plus long d'une image clé : au-delà, la vision la réduit de toute façon.
VISION_MAX_PX = 1568
# Taille de la vignette qui compare deux images (écart moyen des niveaux de gris).
THUMB = (64, 36)


def stamp(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}" if seconds >= 3600 \
        else f"{seconds // 60:02d}:{seconds % 60:02d}"


def key_frames(path: Path, attachments: Path, stem: str, interval: float, threshold: float,
               max_frames: int, warnings: list[str]) -> tuple[list[dict], float]:
    """Images clés : une image toutes les `interval` secondes, gardée si elle
    diffère assez de la dernière gardée."""
    import av
    import numpy as np

    frames, last, next_time, duration = [], None, 0.0, 0.0
    with av.open(str(path)) as container:
        if container.duration:
            duration = container.duration / 1_000_000
        if not container.streams.video:
            return [], duration
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            if frame.time is None or frame.time < next_time:
                continue
            next_time = frame.time + interval
            duration = max(duration, frame.time)
            image = frame.to_image()
            thumb = np.asarray(image.convert("L").resize(THUMB), dtype=np.float32) / 255
            if last is not None and float(np.abs(thumb - last).mean()) < threshold:
                continue
            if len(frames) >= max_frames:
                warnings.append(f"Plus de {max_frames} changements d'écran : images suivantes ignorées "
                                "(augmentez --threshold ou --max-frames)")
                break
            last = thumb
            image.thumbnail((VISION_MAX_PX, VISION_MAX_PX))
            attachments.mkdir(parents=True, exist_ok=True)
            target = attachments / f"{stem}-{len(frames) + 1:02d}.png"
            image.save(target)
            frames.append({"time": round(frame.time, 2), "path": target})
    return frames, duration


def transcribe(path: Path, folder: Path, language: str | None) -> tuple[list[dict], str]:
    from faster_whisper import WhisperModel

    model = WhisperModel(str(folder), device="cpu", compute_type="int8", local_files_only=True)
    segments, info = model.transcribe(str(path), language=language, vad_filter=True)
    return ([{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments if s.text.strip()],
            info.language)


def markdown(path: Path, stem: str, frames: list[dict], segments: list[dict], duration: float,
             note: str) -> str:
    lines = [f"# {path.stem}", "", f"Source : `{path.name}`, durée {stamp(duration)}. {note}", ""]
    if not frames:
        lines += ["## Transcription", ""]
        lines += [f"**{stamp(s['start'])}** {s['text']}" for s in segments] or ["*(aucune parole transcrite)*"]
        return "\n".join(lines) + "\n"
    for index, frame in enumerate(frames):
        end = frames[index + 1]["time"] if index + 1 < len(frames) else float("inf")
        start = frame["time"] if index else float("-inf")
        said = [s["text"] for s in segments if start <= s["start"] < end]
        lines += [f"## {stamp(frame['time'])}", "",
                  f"![{stamp(frame['time'])}](attachments/{frame['path'].name})", "",
                  "<!-- vision : décrire l'écran (application, action montrée, données visibles) -->", ""]
        if said:
            lines += ["> " + " ".join(said), ""]
    return "\n".join(lines).rstrip() + "\n"


def convert(path: Path, out: Path, args) -> dict:
    suffix = path.suffix.lower()
    if suffix not in MEDIA:
        raise ValueError(f"extension {suffix or '(aucune)'} non prise en charge ({', '.join(sorted(MEDIA))})")
    stem = args.stem or path.stem
    report = {"input": str(path), "output": str(out / f"{stem}.md"),
              "type": "video" if suffix in VIDEO else "audio", "engine": "images",
              "duration": 0.0, "images": 0, "segments": 0, "language": None, "model": None,
              "needs_vision": False, "vision_pages": [], "warnings": []}
    frames, duration = key_frames(path, out / "attachments", stem, args.interval, args.threshold,
                                  args.max_frames, report["warnings"]) if suffix in VIDEO else ([], 0.0)
    segments, note = [], "Transcription non faite."
    if not args.no_audio:
        folder = model_store.local_model(args.model)
        if folder is None:
            message = (f"Modèle {args.model} absent du cache local ({model_store.models_root()}) : "
                       f"transcription non faite ; lancez `uv run scripts/doctor.py video --prefetch` "
                       "(skill check-prerequisites)")
            if report["type"] == "audio":
                raise RuntimeError(message)
            report["warnings"].append(message)
        else:
            segments, report["language"] = transcribe(path, folder, args.language)
            report["engine"], report["model"] = "whisper", args.model
            note = f"Transcription locale : {args.model} ({report['language']})."
    if not duration and segments:
        duration = segments[-1]["end"]
    report["duration"], report["images"], report["segments"] = round(duration, 1), len(frames), len(segments)
    report["vision_pages"] = [str(f["path"]) for f in frames]
    report["needs_vision"] = bool(frames)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{stem}.md"
    target.write_text(markdown(path, stem, frames, segments, duration, note), encoding="utf-8", newline="\n")
    result = check(target, obsidian=False)
    report["validation"] = {key: result[key] for key in ("ok", "errors", "warnings")}
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="vidéos ou enregistrements audio")
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--language", help="langue parlée (fr, en...) ; défaut : détectée")
    parser.add_argument("--model", default="whisper-small", help="modèle de model-sources.json")
    parser.add_argument("--no-audio", action="store_true", help="images clés seulement, sans transcription")
    parser.add_argument("--interval", type=float, default=1.0, help="secondes entre deux images comparées")
    parser.add_argument("--threshold", type=float, default=0.06,
                        help="écart moyen (0 à 1) qui fait garder une image")
    parser.add_argument("--max-frames", type=int, default=40, help="images clés au plus par vidéo")
    parser.add_argument("--stem", help=argparse.SUPPRESS)
    args = parser.parse_args()
    results, failed = [], False
    if not args.no_audio:
        try:
            model_store.entry(args.model)
        except model_store.ModelError as error:
            print_report([], errors=[str(error)])
            return 1
    for path in args.files:
        if not path.is_file():
            results.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        try:
            results.append(convert(path.resolve(), args.out.resolve(), args))
        except Exception as error:  # noqa: BLE001 - le rapport doit lister chaque échec
            results.append({"input": str(path), "error": f"{type(error).__name__}: {error}"})
            failed = True
    print_report(results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
