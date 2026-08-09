## TPLink Stats

This project shows the stats from a TPLink router as a web GUI.

Thanks to the [TP-Link-Archer-C6U Python package](https://github.com/AlexandrErohin/TP-Link-Archer-C6U) for making this possible.

### Setup

To run the project, clone the repository and install the dependencies (this example uses [uv](https://docs.astral.sh/uv/)):
```bash
git clone https://github.com/zydezu/tplinkstats
cd tplinkstats
uv venv
source .venv/bin/activate
pip install -r requirements.txt
```

After installing the dependencies, you can run the project using:
```bash
python main.py
```
