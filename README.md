# MATGen — Mobile Application Traffic Generator

MATGen is a lightweight traffic generator that emulates realistic mobile application traffic. It models user interaction states within a session and generates traffic derived from real Android application traces. MATGen extends the browser-based traffic generator proposed in [FWTG](https://gitlab.com/romars1/fwtg) by applying the same user interaction state model to mobile applications. While the state transitions are inherited from FWTG, the traffic characteristics are derived from real Android application traces. In addition, MATGen incorporates hybrid traffic modeling to improve the realism of generated mobile application traffic.

[[MATGen Paper]](https://drive.google.com/file/d/1Ma_Gacq0OB0XXnL_bNBGKVSReLbLl2bi/view?usp=sharing)

---

## Requirements

Python 3.8+

```bash
cd MATGen
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

---

## Run locally

**Terminal 1 — start the server**
```bash
source env/bin/activate
cd server
python hypercorn_server.py 127.0.0.1 8443 HTTPS ../output
```

**Terminal 2 — run the client**
```bash
source env/bin/activate
cd client
python tcp_client.py social_engager 300 127.0.0.1 8443 HTTPS ../output verbose 1
```

### Client arguments

| Argument | Example | Description |
|---|---|---|
| `profile` | `social_engager` | User profile: `social_engager`, `news_follower`, `content_consumer`, `shopper` |
| `duration_s` | `300` | Emulation duration in seconds — any positive integer |
| `server_ip` | `127.0.0.1` | IP address of the server machine — user defined |
| `server_port` | `8443` | Server port — user defined |
| `conn_type` | `HTTPS` | Connection type: `HTTP` or `HTTPS` |
| `output_dir` | `../output` | Output directory path |
| `verbose` | `verbose` | Optional — print per-request logs to screen |
| `client_id` | `1` | Optional — integer ID for this client (default 0) |
| `single_cycle` | `single_cycle` | Optional — run exactly one NI → I → FI cycle then stop, regardless of remaining time |

### Session modes

By default the client runs in **time-based** mode: after completing NI → I → FI it replays FI repeatedly until the emulation duration expires.

With `single_cycle` the client runs in **single-cycle** mode: it completes one NI → I → FI pass and stops immediately, even if time remains.

```bash
# time-based (default) — replays FI until 300s are up
python tcp_client.py social_engager 300 127.0.0.1 8443 HTTPS ../output verbose 1

# single cycle — NI → I → FI → stop
python tcp_client.py social_engager 300 127.0.0.1 8443 HTTPS ../output verbose 1 single_cycle
```

---

## Running multiple clients

To run multiple clients concurrently against the same server, set the correct server
IP and port for your setup, and use a different `client_id` for each client so that
each one writes to its own output folder.

---

## Output

Each run creates a timestamped folder inside the output directory:

```
output/
├── server.log                                        ← server log
└── client_1_20260610_100510/                         ← {client_id}_{timestamp}
    ├── client.log                                    ← client error/info log
    ├── session_summary.log                           ← full statistics summary
    ├── response_flow.csv                             ← per-request log (timestamp, method, IM, size)
    └── client_id_1_interaction_mode_info_session_1_info.csv   ← per-IM statistics
```

---

## Project structure

```
matgenv1/
├── client/
│   ├── tcp_client.py           ← main client script
│   └── module/
│       ├── http_request.py     ← async GET/POST over httpx
│       └── utils/
│           ├── config.py       ← paths, User/Session classes, data loaders
│           ├── interaction_params.py  ← loads JSON config into IMParams
│           ├── rate_size_selection.py ← samples request rate and object size from CSV
│           ├── burst.py        ← BurstController (burst state per direction)
│           ├── im_params.py    ← IMParams / DirectionParams classes
│           └── stats.py        ← EmulationStats, IMRecord, CSV/log export
├── server/
│   └── hypercorn_server.py     ← Quart/Trio HTTP/2 server
├── data/
│   ├── csv/                    ← request rate and object size distributions per app
│   └── json/                   ← burst parameters and data caps per app
├── output/                     ← generated output goes here
├── env/                        ← Python virtual environment
└── requirements.txt
```

---

## Current version

This version models a **single app session** — one user profile, one app category, and one
continuous session progressing through Non-Interactive, Interactive, and Full-Interactive
states. It runs over HTTPS HTTP/2 within a Python-based client-server framework.  Application supports: Facebook (social media category, social_engager user_profile), TikTok (entertainment category, content_consumer user_profile), CNN (news category, news_follower user_profile), and Amazon (e-commerce category, shopper user_profile).

### Todo

- **Multi-app user session model**
- **QoE model** 
- **HTTP/3 support** 
- **Broader app coverage** 

---

## Citation

> Md Tariqul Islam, Christian Esteve Rothenberg, Gyanesh Patra,
> *"Why Realistic Background Traffic Matters: Low-Latency Transport Evaluation with MATGen"*,
> IEEE/IFIP Network Operations and Management Symposium (NOMS) 2026.

```bibtex
@inproceedings{islam2026matgen,
  author    = {Islam, Md Tariqul and Rothenberg, Christian Esteve and Patra, Gyanesh},
  title     = {Why Realistic Background Traffic Matters: Low-Latency Transport Evaluation with {MATGen}},
  booktitle = {Proceedings of the IEEE/IFIP Network Operations and Management Symposium (NOMS)},
  year      = {2026},
  note      = {In press}
}
```

---

## License

SPDX-License-Identifier: GPL-3.0-or-later. See [LICENSE](LICENSE) for full terms.
