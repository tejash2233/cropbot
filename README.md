# CropBot

CropBot is a software-only plant health screening website. It has a welcome page, a camera and photo-upload scanner, an interactive plant guide, and a private scan journal stored in the visitor's browser.

## Pages and features

- `/` — welcome page, how it works, and shortcuts to the main tools.
- `/scanner` — use the current device's front or rear camera, or upload a leaf image; see the top three model matches and care suggestions.
- `/guide` — search and filter the model's supported classes by crop, and expand practical care notes.
- `/journal` — review scans saved in this browser, filter them, and export a CSV.

The browser asks for camera permission only after the visitor starts the camera. Uploaded images are processed in memory and are not saved by the Flask app. Journal entries are stored in local browser storage, not in a server database.

## Model coverage and limitations

The included model's crop list and class count are shown by the live API, scanner, and searchable guide. It is trained on PlantDoc, a small, real-world-style dataset with about 2,600 images across 13 plant types. In the bundled training run, the held-out PlantDoc test split scored 72.5% for crop identification (plant name) and 49.6% for the exact crop-and-disease label across 236 images. These scores are development metrics on a small dataset, not a guarantee on local farm photos. CropBot provides screening suggestions, not a confirmed diagnosis or pesticide recommendation. Confirm significant or spreading symptoms with a local agricultural specialist.

The model and matching class map are in `models/`. Keep both files from the same training run.

## Run locally

Use Python 3.11 and install the dependencies:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Browser camera access works on localhost and HTTPS sites; otherwise choose an image upload.

## Deploy on Render

The repository includes `render.yaml` for a Python web service. In the Render Dashboard:

1. Choose **New → Blueprint** and connect the GitHub repository `tejash2233/cropbot`.
2. Review the service settings and the selected compute plan before applying the Blueprint.
3. Apply it. Render installs `requirements.txt`, starts Gunicorn, and deploys on pushes to the connected Git branch.
4. Open the generated `https://<service>.onrender.com` address. HTTPS allows the browser camera prompt.

The Blueprint selects `1c-2g` (1 CPU, 2 GB RAM) because TensorFlow and the loaded model need more memory than Render's free web plan provides. Render's listed price for that plan is currently about $40/month; confirm the current amount in Render before applying. Render's Python web service guidance is at https://render.com/docs/deploy-flask and compute plan details at https://render.com/docs/compute-plans.

## Deploy on Vercel

This repository is configured for Vercel's Flask Python runtime. Connect `tejash2233/cropbot` as a new Vercel project and deploy from the repository root. Vercel serves the files in `public/` from its CDN; the Flask app serves those same files locally at `/style.css` and `/app.js`.

The classifier uses TensorFlow, so the Python function bundle may exceed Vercel's standard 500 MB limit. If Vercel rejects the build for bundle size, enable **Large Functions** for the project by setting `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` in Project Settings → Environment Variables, then redeploy. Large Functions are a Vercel beta feature and plan/usage limits apply. The hosted scanner resizes and compresses photos in the browser before upload to stay below the function request limit.

The project pins Python 3.12 for Vercel and sets a 60-second function duration. The TensorFlow model is loaded by the Flask function at startup, so allow the first request after a cold start to take longer. For frequent inference or if the project cannot enable large functions, deploy the Flask model API on a Python container host and keep the Vercel site as its frontend.

## Train or replace the classifier

For field-photo training, download the ZIP from the [PlantDoc dataset repository](https://github.com/pratikkayal/PlantDoc-Dataset) and save it as `work/PlantDoc-Dataset.zip`. The included `prepare_plantdoc.py` safely extracts its train/test folders and renames image files that Windows cannot store:

```bash
python prepare_plantdoc.py
```

The dataset repository states CC BY 4.0; keep attribution when redistributing the images. You can also use PlantVillage from Kaggle by arranging it as `datasets/PlantVillage/<class-name>/<image>`.

Train on a computer with Python 3.11 and TensorFlow. Set the data directory before running the trainer:

```bash
# Windows PowerShell
$env:CROPBOT_DATASET_DIR = "datasets/PlantDoc"
python train_model.py

# Linux/macOS
CROPBOT_DATASET_DIR=datasets/PlantDoc python train_model.py
```

The trainer detects PlantDoc's separate train and test folders, maps each label to a plant and condition, fine-tunes MobileNetV2, and saves a `.keras` model plus matching class map in `models/`. Commit both files together to deploy an updated model. The trainer prints held-out validation accuracy; do not interpret that score as proven field accuracy.

Dataset reference: Singh et al., “PlantDoc: A Dataset for Visual Plant Disease Detection,” CoDS-COMAD 2020, [paper](https://arxiv.org/abs/1911.10317), [dataset and license](https://github.com/pratikkayal/PlantDoc-Dataset).

## API

- `GET /api/status` — model readiness and supported crop/class counts.
- `GET /api/diseases` — supported model classes and their care notes.
- `POST /api/scan` — multipart upload with the image field named `image`.
- `GET /healthz` — Render health check.

This app has no user accounts or server-side scan database. The scan journal is browser-local and can be exported or cleared from the Journal page.
