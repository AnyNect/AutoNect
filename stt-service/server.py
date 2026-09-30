"""AutoNect STT service - NVIDIA Parakeet TDT 0.6B v2 (English), ONNX CPU.

Browser streams raw float32 mono PCM 16 kHz over /ws/stt (same transport
as Raji' ASR).  The server accumulates audio, uses RMS endpointing to
find utterance ends, and decodes each utterance with Parakeet TDT.

Protocol (JSON out):
  {"type":"partial","text":...}   interim guess, grows while speaking
  {"type":"final","text":...}     utterance finished (silence detected)
  {"type":"ready"}                on connect, model warm
  {"type":"error","message":...}
Client sends: raw float32 little-endian PCM bytes (mono, 16 kHz).
Send the text "reset" (binary text frame) to clear the buffer.
"""
import os, json, time, asyncio, logging
import numpy as np
import onnx_asr
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import vocab
from scipy.signal import resample_poly

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stt")

SR = 16000
CHUNK_MS = 100
# Endpointing
VAD_RMS = 0.008          # speech threshold (empirical, mirrors Raji' VAD_RMS)
SILENCE_END_S = 0.8      # trailing silence that ends an utterance
MIN_UTTER_S = 0.3        # ignore blips shorter than this
MAX_UTTER_S = 30.0       # hard cap so a monologue still flushes
PARTIAL_EVERY_S = 0.6    # re-decode cadence for interim text

MODEL_ID = os.environ.get("STT_MODEL", "nemo-parakeet-tdt-0.6b-v2")

app = FastAPI()
model = None


def rms(x):
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


@app.on_event("startup")
def _load():
    global model
    t = time.time()
    log.info("Loading %s (int8)...", MODEL_ID)
    model = onnx_asr.load_model(MODEL_ID, quantization="int8")
    log.info("Model ready in %.1fs", time.time() - t)


@app.post("/reload-vocab")
def reload_vocab():
    n = vocab.reload_vocab()
    log.info("Reloaded dictionary: %d aliases", n)
    return {"aliases": n}


def _decode(a: np.ndarray) -> str:
    if len(a) < int(MIN_UTTER_S * SR):
        return ""
    txt = model.recognize(a, sample_rate=SR)
    return vocab.correct((txt or "").strip())


@app.websocket("/ws/stt")
async def ws_stt(ws: WebSocket):
    await ws.accept()
    # Browser tells us its real AudioContext rate; we resample to 16k.
    try:
        client_sr = int(ws.query_params.get("sr", SR))
    except ValueError:
        client_sr = SR
    if client_sr <= 0:
        client_sr = SR
    await ws.send_json({"type": "ready", "sr": client_sr})
    buf = np.zeros(0, dtype=np.float32)
    speech_started = False
    last_voice = time.time()
    last_partial = 0.0
    loop = asyncio.get_event_loop()
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            text = msg.get("text")
            if text == "reset":
                buf = np.zeros(0, dtype=np.float32)
                speech_started = False
                # Distinct ack so the client can drop every frame that
                # was already in flight before this reset (WebSocket is
                # ordered, so anything before the ack is stale).
                await ws.send_json({"type": "reset-ack"})
                continue
            if not data:
                continue
            chunk = np.frombuffer(data, dtype=np.float32)
            _nchunks = getattr(ws.state, "n", 0) + 1
            ws.state.n = _nchunks
            if _nchunks <= 3 or _nchunks % 30 == 0:
                log.info("chunk %d: %d samples, peak=%.4f, buf=%.1fs",
                         _nchunks, len(chunk),
                         float(np.max(np.abs(chunk))) if len(chunk) else 0.0,
                         len(buf) / SR)
            if client_sr != SR and len(chunk):
                from math import gcd
                g = gcd(client_sr, SR)
                chunk = resample_poly(chunk, SR // g, client_sr // g).astype(np.float32)
            buf = np.concatenate([buf, chunk]) if len(buf) else chunk.copy()
            # cap
            if len(buf) > int(MAX_UTTER_S * SR):
                buf = buf[-int(MAX_UTTER_S * SR):]
            now = time.time()
            loud = rms(chunk) > VAD_RMS
            if loud:
                speech_started = True
                last_voice = now
            # partial while speaking
            if speech_started and (now - last_partial) > PARTIAL_EVERY_S and len(buf) > int(MIN_UTTER_S * SR):
                last_partial = now
                a = buf.copy()
                txt = await loop.run_in_executor(None, _decode, a)
                if txt:
                    await ws.send_json({"type": "partial", "text": txt})
            # endpoint
            if speech_started and (now - last_voice) > SILENCE_END_S:
                a = buf.copy()
                txt = await loop.run_in_executor(None, _decode, a)
                await ws.send_json({"type": "final", "text": txt})
                buf = np.zeros(0, dtype=np.float32)
                speech_started = False
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("ws error")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
