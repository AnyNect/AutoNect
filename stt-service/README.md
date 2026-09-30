# AutoNect STT service

Local speech-to-text for AutoNect's mic dictation button.

Model: NVIDIA **Parakeet TDT 0.6B v2** (English), ONNX Runtime, CPU,
int8.  ~17x realtime on CPU; no GPU, no cloud, no PyTorch at inference.

## Run

    cd stt-service
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 6012

Listens on :6012.  AutoNect's mic button streams 16 kHz float32 PCM to
`/ws/stt` and writes the transcript into the prompt.

## Protocol

Client sends raw float32 mono PCM over the WebSocket, plus `?sr=<rate>`
(the browser's real AudioContext rate; the server resamples to 16 kHz).
Server sends JSON:

    {"type":"ready","sr":<client rate>}
    {"type":"partial","text":"..."}   interim, grows while speaking
    {"type":"final","text":"..."}     utterance ended (silence detected)

A text frame `reset` clears the buffer.

## Notes

- Endpointing is RMS-based (VAD_RMS, SILENCE_END_S in server.py).  The
  model itself is utterance-based, not streaming.
- The browser must be in a secure context for mic access: use
  `http://127.0.0.1`/`localhost`, NOT a LAN IP.
- Functional end-to-end verified via the browser path (chunks arrive,
  transcript renders).  Model accuracy on the JFK clip is exact.
