<h1 align="center">RipeRadar</h1>

<p align="center"><b>Snap your fruit &amp; veg, and find out exactly when to eat it.</b></p>

<p align="center">
  <a href="https://devpost.com/software/riperadar"><img src="https://img.shields.io/badge/Devpost-Submission-003E54?logo=devpost&logoColor=white" alt="Devpost submission"></a>
  <a href="https://youtu.be/_8mLmJ7hfnQ"><img src="https://img.shields.io/badge/YouTube-Demo%20video-FF0000?logo=youtube&logoColor=white" alt="Demo video"></a>
  <img src="https://img.shields.io/badge/Banana%20Hacks-2026-F5C518" alt="Banana Hacks 2026">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white" alt="OpenCV">
  <img src="https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/CLIP-Hugging%20Face-FFD21E?logo=huggingface&logoColor=black" alt="CLIP via Hugging Face">
  <img src="https://img.shields.io/badge/Gemini-8E75B2?logo=googlegemini&logoColor=white" alt="Gemini">
</p>

RipeRadar is an image-AI web app that finds every produce item in a photo, measures its colour and bruising,
scores ripeness 0–100, predicts how many days you have left, and builds a "use-it-up" plan so less food ends up
in the bin.

- **Submission:** https://devpost.com/software/riperadar
- **Demo video:** https://youtu.be/_8mLmJ7hfnQ
- Built for **Banana Hacks 2026** (Image AI theme).

## Why
Roughly a third of food is wasted, and fresh produce is the biggest share at home. Usually that's not because
people don't care. They just don't know what is about to turn. RipeRadar makes that visible.

## How it works
1. **Segment:** the background colour is estimated from the frame border. Lab colour distance plus saturation
   seeds an OpenCV **GrabCut** mask, and morphology splits the mask into individual items.
2. **Measure:** per-item HSV analysis gives the green/yellow/red share of the skin. Adaptive darkness and
   brown-hue detection map bruises and sugar spots (shown as a red heat-map overlay).
3. **Identify:** each crop goes through **CLIP ViT-B/32** zero-shot on CPU, which predicts *what* the item is
   (18 produce types) and *which condition* it looks like (unripe / ripe / overripe / rotten).
4. **Fuse:** a per-produce model combines the colour score and the CLIP condition score into a ripeness index.
   For example, "green = unripe" holds for bananas but not for apples, and "yellow = decay" holds for broccoli.
5. **Shelf life:** days-until-ripe and days-left are computed for counter vs. fridge storage.
6. **Plan:** the structured vision results are sent to **Gemini**, which writes a recipe that uses the most
   urgent items. Offline tips are shown if no key is set.
7. **Pantry:** tracked items count down over time in an eat-first list, along with a "waste avoided" score.

Everything visual runs locally on a laptop CPU (no GPU needed). One scan takes about 1–2 s.

## Run it
```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
copy .env.example .env        # optional: add your free Gemini key
uvicorn riperadar.main:app --port 8000
```
Open http://localhost:8000.

## Tech
Python · FastAPI · OpenCV · PyTorch · Hugging Face Transformers (CLIP) · Google Gemini · vanilla HTML/CSS/JS

Sample images are from Wikimedia Commons (CC licences).
