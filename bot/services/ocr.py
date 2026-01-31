from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FRAMES_PER_SECOND = 8
_FRAME_SECONDS = 2
_MAX_TEXT_LENGTH = 1000
_MIN_LINE_LENGTH = 3
_MIN_ALNUM_COUNT = 3
_MIN_ALNUM_RATIO = 0.35
_MAX_JUNK_RATIO = 0.35
_JUNK_CHARS = set(r"@|\/=_*[]{}^~")


class TesseractUnavailable(RuntimeError):
    """Raised when tesseract is not available or fails to run."""


def extract_frames(video_path: Path, out_dir: Path, task_id: int) -> list[Path]:
    """Extract frames from the first seconds of a video."""

    out_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = out_dir / f"task_{task_id}_%03d.png"
    filter_chain = (
        f"fps={_FRAMES_PER_SECOND},"
        "scale=1280:-1,"
        "format=gray,"
        "eq=contrast=1.3:brightness=0.05"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        filter_chain,
        "-t",
        str(_FRAME_SECONDS),
        str(frame_pattern),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    frames = sorted(out_dir.glob(f"task_{task_id}_*.png"))
    return frames


def run_tesseract(image_path: Path) -> str:
    """Run tesseract against a single image and return raw text."""

    if not shutil.which("tesseract"):
        raise TesseractUnavailable("tesseract not found")

    def _execute(lang: str) -> str:
        result = subprocess.run(
            [
                "tesseract",
                str(image_path),
                "stdout",
                "-l",
                lang,
                "--oem",
                "1",
                "--psm",
                "6",
                "-c",
                "preserve_interword_spaces=1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    try:
        return _execute("rus+eng")
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or "").lower()
        if "failed loading language" in error_text or "error opening data file" in error_text:
            return _execute("eng")
        raise TesseractUnavailable(str(exc)) from exc


def _line_is_noisy(line: str) -> bool:
    if not line:
        return True
    line_length = len(line)
    if line_length < _MIN_LINE_LENGTH:
        return True
    alnum_count = sum(1 for char in line if char.isalpha() or char.isdigit())
    junk_count = sum(1 for char in line if char in _JUNK_CHARS)
    if alnum_count < _MIN_ALNUM_COUNT:
        return True
    alnum_ratio = alnum_count / line_length
    junk_ratio = junk_count / line_length
    return alnum_ratio < _MIN_ALNUM_RATIO or junk_ratio > _MAX_JUNK_RATIO


def _clean_text(text: str) -> str:
    seen: set[str] = set()
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _line_is_noisy(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        cleaned_lines.append(line)
    result = "\n".join(cleaned_lines).strip()
    if len(result) > _MAX_TEXT_LENGTH:
        result = result[:_MAX_TEXT_LENGTH].rstrip()
    return result


def pick_best_text(texts: list[str]) -> str:
    """Pick the longest cleaned OCR result."""

    best = ""
    for text in texts:
        cleaned = _clean_text(text)
        if len(cleaned) > len(best):
            best = cleaned
    return best


def ocr_video_first_frames(video_path: Path, task_id: int) -> str:
    """Run OCR on the first frames of a video and return best text."""

    frames_root = Path("bot/storage/ocr_frames")
    frames_dir = frames_root / f"task_{task_id}"
    frames: list[Path] = []
    try:
        frames = extract_frames(video_path, frames_dir, task_id)
        logger.info("ocr frames extracted task_id %s count %s", task_id, len(frames))
        texts: list[str] = []
        for frame in frames:
            try:
                texts.append(run_tesseract(frame))
            except TesseractUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - best effort per frame
                logger.error("ocr failed task_id %s error %s", task_id, exc)
        return pick_best_text(texts)
    finally:
        if frames_dir.exists():
            shutil.rmtree(frames_dir, ignore_errors=True)


def ocr_image(image_path: Path, task_id: int) -> str:
    """Run OCR on a single image."""

    try:
        return pick_best_text([run_tesseract(image_path)])
    except TesseractUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - best effort for OCR
        logger.error("ocr failed task_id %s error %s", task_id, exc)
        return ""
