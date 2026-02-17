"""
Vision WebSocket — Real-time camera frame processing via YOLO.

Dedicated /ws/vision endpoint (separate from main /ws to avoid flooding).
Browser sends base64 JPEG frames, server runs YOLO inference in thread pool,
returns JSON detections with normalized coordinates (0-1).
"""

import asyncio
import base64
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nex.utils.logger import setup_logger

logger = setup_logger(__name__)

vision_ws_router = APIRouter()

AUTH_TIMEOUT = 5


async def _authenticate(ws: WebSocket) -> bool:
    """Wait for auth message within timeout."""
    from nex.api.server import session_token

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") == "auth" and msg.get("token") == session_token:
            return True
        logger.warning("Vision WS auth failed: invalid token")
        return False
    except asyncio.TimeoutError:
        logger.warning("Vision WS auth failed: timeout")
        return False
    except Exception as e:
        logger.warning(f"Vision WS auth failed: {e}")
        return False


def _decode_frame(data_b64: str):
    """Decode base64 JPEG to numpy array."""
    import cv2
    import numpy as np

    try:
        img_bytes = base64.b64decode(data_b64)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


def _run_detect(frame, conf_threshold: float) -> dict:
    """Run YOLO detection, return JSON-serializable result."""
    from nex.api.vision_tools import _get_detect_model

    model = _get_detect_model()
    results = model.predict(frame, imgsz=640, verbose=False, conf=conf_threshold)

    if not results or len(results[0].boxes) == 0:
        return {"detections": [], "mode": "detect"}

    detections = []
    r = results[0]
    h, w = frame.shape[:2]

    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        name = r.names[cls_id]
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        detections.append({
            "class": name,
            "confidence": round(conf, 3),
            "bbox": [
                round(x1 / w, 4),
                round(y1 / h, 4),
                round(x2 / w, 4),
                round(y2 / h, 4),
            ],
        })

    return {"detections": detections, "mode": "detect"}


def _run_segment(frame, conf_threshold: float) -> dict:
    """Run YOLO segmentation, return detections with polygon masks."""
    import cv2
    import numpy as np
    from nex.api.vision_tools import _get_seg_model

    model = _get_seg_model()
    results = model.predict(frame, imgsz=640, verbose=False, conf=conf_threshold)

    if not results or len(results[0].boxes) == 0:
        return {"detections": [], "mode": "segment"}

    detections = []
    r = results[0]
    h, w = frame.shape[:2]

    masks = r.masks
    for i, box in enumerate(r.boxes):
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        name = r.names[cls_id]
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        det = {
            "class": name,
            "confidence": round(conf, 3),
            "bbox": [
                round(x1 / w, 4),
                round(y1 / h, 4),
                round(x2 / w, 4),
                round(y2 / h, 4),
            ],
        }

        # Add simplified polygon mask
        if masks is not None and i < len(masks.xy):
            polygon = masks.xy[i]
            if len(polygon) > 0:
                # Simplify polygon with approxPolyDP
                polygon_int = polygon.astype(np.int32)
                epsilon = 0.02 * cv2.arcLength(polygon_int, True)
                approx = cv2.approxPolyDP(polygon_int, epsilon, True)
                # Normalize to 0-1
                points = []
                for pt in approx:
                    px, py = pt[0]
                    points.append([round(float(px) / w, 4), round(float(py) / h, 4)])
                det["polygon"] = points

        detections.append(det)

    return {"detections": detections, "mode": "segment"}


def _run_classify(frame, conf_threshold: float) -> dict:
    """Run YOLO classification, return top-5 classes."""
    from nex.api.vision_tools import _get_cls_model

    model = _get_cls_model()
    results = model.predict(frame, imgsz=640, verbose=False)

    if not results or results[0].probs is None:
        return {"classifications": [], "mode": "classify"}

    probs = results[0].probs
    top5_indices = probs.top5
    top5_confs = probs.top5conf.tolist()
    names = results[0].names

    classifications = []
    for idx, conf in zip(top5_indices, top5_confs):
        if conf >= conf_threshold:
            classifications.append({
                "class": names[idx],
                "confidence": round(conf, 3),
            })

    return {"classifications": classifications, "mode": "classify"}


@vision_ws_router.websocket("/ws/vision")
async def vision_websocket(ws: WebSocket):
    """WebSocket endpoint for real-time vision processing."""
    await ws.accept()

    if not await _authenticate(ws):
        await ws.send_text(json.dumps({
            "type": "error",
            "message": "Authentication required.",
        }))
        await ws.close(code=4001, reason="Authentication failed")
        return

    logger.info("Vision WebSocket client connected")
    await ws.send_text(json.dumps({"type": "vision.connected"}))

    processing = False

    try:
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "frame":
                continue

            # Backpressure: drop frame if still processing previous one
            if processing:
                continue

            processing = True
            try:
                frame_data = msg.get("data", "")
                mode = msg.get("mode", "detect")
                conf_threshold = msg.get("confidence", 0.25)

                t0 = time.monotonic()

                # Decode frame in thread pool
                frame = await asyncio.to_thread(_decode_frame, frame_data)
                if frame is None:
                    processing = False
                    continue

                # Run inference in thread pool
                if mode == "segment":
                    result = await asyncio.to_thread(_run_segment, frame, conf_threshold)
                elif mode == "classify":
                    result = await asyncio.to_thread(_run_classify, frame, conf_threshold)
                else:
                    result = await asyncio.to_thread(_run_detect, frame, conf_threshold)

                elapsed_ms = round((time.monotonic() - t0) * 1000)
                result["type"] = "vision.result"
                result["inference_ms"] = elapsed_ms

                await ws.send_text(json.dumps(result))

            except Exception as e:
                logger.error(f"Vision frame error: {e}")
            finally:
                processing = False

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Vision WS error: {e}")
    finally:
        logger.info("Vision WebSocket client disconnected")
