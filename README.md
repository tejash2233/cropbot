# CropBot

Flask dashboard for leaf disease screening and Raspberry Pi field monitoring. The site can use a phone/laptop camera or upload, and can request a capture from a camera attached to the Pi. A model must be trained first; the app deliberately reports when a real model is missing rather than presenting invented predictions.

## Project files

```text
app.py                 Flask routes, model inference, sensor and pump APIs
train_model.py         Train MobileNetV2 from a class-folder dataset
hardware/device.py     GPIO17 soil, GPIO27 rain, GPIO22 active-low relay
templates/index.html   Interactive dashboard
static/                Responsive styles and browser camera controls
models/                Put plant_disease_model.keras and class_indices.json here
```

## Dataset and training

Download a PlantVillage dataset from Kaggle and arrange it as `datasets/PlantVillage/<class name>/image.jpg`. Train on a desktop/laptop with TensorFlow installed; training on a Pi 3B+ is slow and memory constrained. From the project directory:

```bash
py -3.13 -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS use: python3.13 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python train_model.py
```

Copy the generated `models/plant_disease_model.keras` and `models/class_indices.json` to the Pi. The classifier is a screening aid; its suggestions are conservative and are not a substitute for local agronomic diagnosis.

Use Python 3.13 or 3.12 for TensorFlow. Python 3.14 is not currently a supported Windows TensorFlow target. If the project has no trained model files, disease classification cannot return real results; the dashboard status and scan response will state what file is missing.

## Run on a computer

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://127.0.0.1:5000`. Camera access in a browser requires a secure context (localhost or HTTPS). On a phone connected to the Pi, use the Pi's local IP; browser camera access may require HTTPS, so the Upload photo option is the reliable fallback over plain local HTTP.

## Host the website on Google Cloud Run

Cloud Run can host the Flask website and API. It does not have access to the Raspberry Pi's GPIO, attached Pi camera, or sensors. In Cloud Run the hardware endpoints run in simulation mode unless you build a separate, secured connection from the cloud app to the Pi.

1. Install and sign in to the Google Cloud CLI, create/select a Google Cloud project, and enable billing for that project.
2. If you want disease scans, train the model and copy `models/plant_disease_model.keras` and `models/class_indices.json` into this folder first. Without both files the site opens, but scans report that no trained model is available.
3. In PowerShell, deploy this folder:

   ```powershell
   cd C:\path\to\outputs
   gcloud init
   gcloud run deploy cropbot --source .
   ```

   Follow the prompts to select the project and a nearby region. Choose public access only if you want anyone with the URL to open it. Cloud Run prints an HTTPS URL when deployment completes.

This project has no login or API authentication. If made public, anyone can send requests to its APIs (including model scans), which may use your Cloud Run resources. Do not connect public pump/motor endpoints directly to your Pi. Add authentication and a private, secured device connection before enabling remote hardware control. Camera permission in a browser is granted by the user on their device; Pi camera index capture is not available inside Cloud Run.

## Raspberry Pi 3B+

Connect the Pi to the same Wi-Fi router as your phone/laptop, copy the project and model, create a virtual environment, install compatible dependencies for your Raspberry Pi OS, and run `python app.py`. Then find its address with `hostname -I` and visit `http://<pi-ip>:5000`. To install the system service, run `sudo python3 setup_pi.py` from this directory.

TensorFlow wheels vary by Raspberry Pi OS, Python version and CPU architecture. The requirements file intentionally avoids forcing a heavyweight TensorFlow build on a Pi. Install a compatible TensorFlow/TFLite runtime for your OS, or run inference on a separate computer and use the Pi for camera and GPIO. The current app expects the Keras `.keras` model.

## Supplied wiring supported by this code

| Function | BCM GPIO | Physical pin |
|---|---:|---:|
| Soil digital output | 17 | 11 |
| Rain digital output | 27 | 13 |
| Active-low relay input | 22 | 15 |

The supplied motor wiring was incomplete, so motor movement is intentionally not enabled. L293D requires defined direction and enable (ENA/ENB) connections; do not energize motor outputs until those pins and a suitable motor supply are specified. GPIO pins are 3.3V logic and must not receive 5V sensor outputs. Use a separate, correctly rated motor/pump supply and common ground where required by the driver/relay design; never power a pump from Pi GPIO. Confirm relay isolation, pump current, diode polarity, and sensor output voltage with your module documentation before powering it.

GPIO sensor interpretation can vary by module; `hardware/device.py` assumes the digital output is active-low (LOW means dry / rain detected). Adjust to match the sensor's comparator setting. Pump API automatically limits each activation to 10 seconds; it does not automatically water based on sensors.

## Camera selection

“This device” uses the browser camera with the environment-facing camera requested on phones; choose the camera in the browser/device settings, or use Upload photo. “Raspberry Pi” asks OpenCV for camera index 0 or 1, generally USB cameras. CSI camera support depends on OS and camera stack; enable it and test it separately. The phone's browser camera is not passed through the Pi server.

## API

- `POST /api/scan` multipart image field `image`
- `POST /api/camera-scan` JSON `{"camera_id":0}` or `1`
- `GET /api/status`, `GET /api/sensors`, `GET /api/history`
- `POST /api/pump` JSON `{"action":"on","seconds":3}` or `{"action":"off"}`
- `POST /api/motor` accepts direction, but the hardware adapter reports motor control unavailable until wiring is defined.
