---
title: VeloClip Core Engine
emoji: ⚡
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# VeloClip Core Engine (24/7 Cloud Media Processor)

High-speed, zero-storage media extraction and processing microservice built for [VeloClip](https://veloclip-media.vercel.app/).

## Capabilities
- **Direct 1080p & 4K MP4 Processing**: Native FFmpeg muxing merges video and audio into a single playable container.
- **Stem Audio Extraction**: High-fidelity 320kbps MP3 audio transcoding.
- **Anti-Bot Engine**: Multi-client rotation (`android`, `ios`, `mweb`, `web_creator`).
- **Zero-Storage Buffer**: Streams directly through HTTP chunked transfer without caching to disk.

## Endpoints
- `GET /api/health` — Service heartbeat and status check
- `POST /api/extract` — Media URL analysis and stream generation
- `GET /api/stream` — Zero-storage live stream tunneling
- `GET /api/download` — FFmpeg-powered MP4/MP3 download service
