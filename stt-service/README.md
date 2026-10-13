# AutoNect STT service

<p align="center">
  <img src="https://img.shields.io/badge/Parakeet-TDT%200.6B%20v2-76B900?style=flat&logo=nvidia&logoColor=white" alt="Parakeet">
  <img src="https://img.shields.io/badge/ONNX-Runtime-005CED?style=flat&logo=onnx&logoColor=white" alt="ONNX">
  <img src="https://img.shields.io/badge/int8-CPU-0a4740?style=flat" alt="int8 CPU">
  <img src="https://img.shields.io/badge/realtime-17x-10b981?style=flat" alt="17x realtime">
  <img src="https://img.shields.io/badge/cloud-none-6b7280?style=flat" alt="No cloud">
</p>

**Local speech-to-text for AutoNect's mic dictation button.** No cloud,
no GPU, no PyTorch at inference.

---

## Model

| | |
|---|---|
| **Model** | NVIDIA **Parakeet TDT 0.6B v2** (English) |
| **Runtime** | ONNX Runtime, int8 quantised |
| **Device** | CPU |
| **Speed** | about 17x realtime |
| **Endpointing** | RMS-based VAD (the model is utterance-based, not streaming) |

---

## Run

    cd stt-service
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 6012

Listens on **:6012**. AutoNect's mic button streams 16 kHz float32 PCM
to `/ws/stt` and writes the transcript into the prompt.

---

## Protocol

Client sends raw float32 mono PCM over the WebSocket, plus `?sr=<rate>`
(the browser's real `AudioContext` rate; the server resamples to
16 kHz).

Server sends JSON:

    {"type":"ready","sr":<client rate>}
    {"type":"partial","text":"..."}   interim, grows while speaking
    {"type":"final","text":"..."}     utterance ended (silence detected)

A text frame `reset` clears the buffer.

---

## Notes

- Endpointing is RMS-based (`VAD_RMS`, `SILENCE_END_S` in `server.py`).
- The browser must be in a **secure context** for mic access: use
  `http://127.0.0.1` or `localhost`, not a LAN IP.
- Functional end-to-end verified via the browser path (chunks arrive,
  transcript renders). Model accuracy on the JFK clip is exact.
