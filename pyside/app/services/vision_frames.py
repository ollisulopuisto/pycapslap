"""Suggests thumbnail frames from a video with Apple's Vision framework (macOS only).

Samples a frame every ``interval_seconds``, finds the faces in it, and scores the
best face of each frame: Vision's capture quality (what Photos uses for Top Shot),
a sharpness proxy, the expression (smile, open mouth, raised eyebrows) and the
gesture (a raised hand, most of all a pointing one). The ranking rules live in
``frame_scoring``, so they can be tested on any platform.

Adapted from youthumber's video scanner. Only the people grouping is left out: a
thumbnail is one frame of the whole video, not a frame of one speaker.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

from framescore import (
    FrameCandidate,
    assign_hands_to_faces,
    expression_score,
    gesture_score,
    head_shoulders_box,
    rank_candidates,
    sharpness,
)

logger = logging.getLogger(__name__)

MIN_FACE_HEIGHT_RATIO = 0.08  # ignore faces smaller than this share of the frame height
IDENTITY_CROP_MARGIN = 0.1  # tight crop for the sharpness measure
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_SUGGESTIONS = 12
SUGGESTION_WIDTH = 320

_FRAMEWORKS = ("AVFoundation", "CoreMedia", "Foundation", "Quartz", "Vision")

# Only whether the bindings are installed: importing them takes ~300 ms, which
# the window would pay at every start for a feature used now and then. The
# functions below import what they use, on the scanning thread.
HAS_VISION = sys.platform == "darwin" and all(
    importlib.util.find_spec(name) is not None for name in _FRAMEWORKS
)
if sys.platform == "darwin" and not HAS_VISION:
    logger.warning("Apple Vision is not available for frame suggestions")


@dataclass
class SuggestedFrame:
    time_seconds: float
    scores: dict[str, float]
    jpeg: bytes


def cgimage_to_qimage(cg_image) -> QImage:
    """A CGImage as a QImage, through a lossless PNG round trip."""
    import Quartz

    data = Quartz.CFDataCreateMutable(None, 0)
    dest = Quartz.CGImageDestinationCreateWithData(data, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, cg_image, None)
    Quartz.CGImageDestinationFinalize(dest)
    return QImage.fromData(bytes(data))


def _crop_cgimage(cg_image, box: tuple[int, int, int, int]):
    import Quartz

    left, top, right, bottom = box
    return Quartz.CGImageCreateWithImageInRect(
        cg_image, Quartz.CGRectMake(left, top, right - left, bottom - top)
    )


def _make_generator(video_path: str):
    import AVFoundation
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(video_path)
    asset = AVFoundation.AVURLAsset.alloc().initWithURL_options_(url, None)
    generator = AVFoundation.AVAssetImageGenerator.alloc().initWithAsset_(asset)
    generator.setAppliesPreferredTrackTransform_(True)
    return asset, generator


def _grab_at(generator, seconds: float):
    import CoreMedia

    time_value = CoreMedia.CMTimeMakeWithSeconds(seconds, 600)
    cg_image, _error = generator.copyCGImageAtTime_actualTime_error_(
        time_value, None, None
    )
    return cg_image


def _landmark_points(region) -> list[tuple[float, float]]:
    # normalizedPoints() is an unsized C array in PyObjC: read exactly pointCount()
    # entries, iterating it directly runs off the end and crashes the process.
    if region is None:
        return []
    raw = region.normalizedPoints()
    return [(float(raw[i].x), float(raw[i].y)) for i in range(region.pointCount())]


def _landmarks(observation) -> dict[str, list[tuple[float, float]]]:
    landmarks = observation.landmarks() if hasattr(observation, "landmarks") else None
    if landmarks is None:
        return {}
    return {
        "outerLips": _landmark_points(landmarks.outerLips()),
        "innerLips": _landmark_points(landmarks.innerLips()),
        "leftEyebrow": _landmark_points(landmarks.leftEyebrow()),
        "leftEye": _landmark_points(landmarks.leftEye()),
    }


def _joint(observation, name) -> tuple[float, float, float] | None:
    point, _error = observation.recognizedPointForJointName_error_(name, None)
    if point is None:
        return None
    location = point.location()
    return (float(location.x), float(location.y), float(point.confidence()))


def _hand_joints(observation) -> dict[str, tuple[float, float, float]]:
    import Vision

    names = {
        "wrist": Vision.VNHumanHandPoseObservationJointNameWrist,
        "indexMCP": Vision.VNHumanHandPoseObservationJointNameIndexMCP,
        "indexTip": Vision.VNHumanHandPoseObservationJointNameIndexTip,
        "middleMCP": Vision.VNHumanHandPoseObservationJointNameMiddleMCP,
        "middleTip": Vision.VNHumanHandPoseObservationJointNameMiddleTip,
        "ringMCP": Vision.VNHumanHandPoseObservationJointNameRingMCP,
        "ringTip": Vision.VNHumanHandPoseObservationJointNameRingTip,
        "littleMCP": Vision.VNHumanHandPoseObservationJointNameLittleMCP,
        "littleTip": Vision.VNHumanHandPoseObservationJointNameLittleTip,
    }
    joints = {key: _joint(observation, name) for key, name in names.items()}
    return {key: value for key, value in joints.items() if value is not None}


def _body_joints(observation) -> dict:
    import Vision

    wrists = [
        _joint(observation, Vision.VNHumanBodyPoseObservationJointNameLeftWrist),
        _joint(observation, Vision.VNHumanBodyPoseObservationJointNameRightWrist),
    ]
    return {
        "nose": _joint(observation, Vision.VNHumanBodyPoseObservationJointNameNose),
        "wrists": [w for w in wrists if w is not None],
    }


def _analyse_frame(cg_image, width: int, height: int) -> list[dict]:
    """Every usable face in a frame: its box, capture quality, expression and gesture."""
    import Vision

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )
    quality = (
        Vision.VNDetectFaceCaptureQualityRequest.alloc().initWithCompletionHandler_(
            None
        )
    )
    success, _error = handler.performRequests_error_([quality], None)
    if not success:
        return []
    faces = [
        f
        for f in (quality.results() or [])
        if f.boundingBox().size.height >= MIN_FACE_HEIGHT_RATIO
    ]
    if not faces:
        return []

    landmarks = Vision.VNDetectFaceLandmarksRequest.alloc().initWithCompletionHandler_(
        None
    )
    landmarks.setInputFaceObservations_(faces)
    hands = Vision.VNDetectHumanHandPoseRequest.alloc().initWithCompletionHandler_(None)
    hands.setMaximumHandCount_(6)
    bodies = Vision.VNDetectHumanBodyPoseRequest.alloc().initWithCompletionHandler_(
        None
    )
    handler.performRequests_error_([landmarks, hands, bodies], None)

    observed = list(landmarks.results() or []) or faces
    boxes = []
    for f in observed:
        b = f.boundingBox()
        boxes.append(
            (
                float(b.origin.x),
                float(b.origin.y),
                float(b.size.width),
                float(b.size.height),
            )
        )

    hand_list = [
        h for h in (_hand_joints(o) for o in (hands.results() or [])) if "wrist" in h
    ]
    body_list = [_body_joints(o) for o in (bodies.results() or [])]
    owners = assign_hands_to_faces(
        boxes, body_list, [h["wrist"][:2] for h in hand_list]
    )
    aspect = width / height if height else 16 / 9

    analysed = []
    for i, (observation, box) in enumerate(zip(observed, boxes)):
        own_hands = [hand for hand, owner in zip(hand_list, owners) if owner == i]
        analysed.append(
            {
                "bbox": box,
                "quality": float(observation.faceCaptureQuality() or 0.0),
                "expression": expression_score(_landmarks(observation)),
                "gesture": max(
                    (gesture_score(h, box, aspect) for h in own_hands), default=0.0
                ),
            }
        )
    return analysed


def _sharpness(image: QImage) -> float:
    """Variance of a simple edge measure on a small grey copy: higher is sharper."""
    small = image.scaledToWidth(
        96, Qt.TransformationMode.SmoothTransformation
    ).convertToFormat(QImage.Format.Format_Grayscale8)
    return sharpness(
        bytes(small.constBits()), small.width(), small.height(), small.bytesPerLine()
    )


def _jpeg(image: QImage, width: int) -> bytes:
    thumb = image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    thumb.save(buffer, "JPEG", 85)
    return bytes(buffer.data())


def scan_frames(
    video_path: str,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    top: int = DEFAULT_SUGGESTIONS,
    progress: Callable[[float], None] | None = None,
) -> list[SuggestedFrame]:
    """Samples the video and returns the ``top`` best frames, best first, each with a
    small JPEG and its scores. Raises RuntimeError where Vision is not available."""
    if not HAS_VISION:
        raise RuntimeError("Frame suggestions need macOS with Apple Vision")

    import CoreMedia
    import Quartz

    asset, generator = _make_generator(video_path)
    duration = CoreMedia.CMTimeGetSeconds(asset.duration())
    if duration <= 0:
        raise RuntimeError("Could not read the video duration")

    candidates: list[FrameCandidate] = []
    t = min(interval_seconds / 2, duration / 2)
    while t < duration:
        cg_image = _grab_at(generator, t)
        if cg_image is not None:
            width = Quartz.CGImageGetWidth(cg_image)
            height = Quartz.CGImageGetHeight(cg_image)
            faces = []
            for face in _analyse_frame(cg_image, width, height):
                box = head_shoulders_box(
                    face["bbox"],
                    width,
                    height,
                    side=IDENTITY_CROP_MARGIN,
                    above=IDENTITY_CROP_MARGIN,
                    below=IDENTITY_CROP_MARGIN,
                )
                if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                    continue
                crop = _crop_cgimage(cg_image, box)
                face["sharpness"] = _sharpness(cgimage_to_qimage(crop))
                faces.append(face)
            if faces:
                best = max(faces, key=lambda f: f["quality"])
                candidates.append(
                    FrameCandidate(
                        time_seconds=t,
                        quality=best["quality"],
                        expression=best["expression"],
                        gesture=best["gesture"],
                        sharpness=best["sharpness"],
                    )
                )
        t += interval_seconds
        if progress is not None:
            progress(0.95 * min(t / duration, 1.0))

    chosen = rank_candidates(candidates)[:top]
    suggestions = []
    for candidate in chosen:
        cg_image = _grab_at(generator, candidate.time_seconds)
        if cg_image is None:
            continue
        picture = cgimage_to_qimage(cg_image)
        suggestions.append(
            SuggestedFrame(
                time_seconds=round(candidate.time_seconds, 2),
                scores={
                    "quality": round(candidate.quality, 3),
                    "expression": round(candidate.expression, 3),
                    "gesture": round(candidate.gesture, 3),
                    "sharpness": round(candidate.sharpness, 1),
                },
                jpeg=_jpeg(picture, SUGGESTION_WIDTH),
            )
        )
    if progress is not None:
        progress(1.0)
    return suggestions
