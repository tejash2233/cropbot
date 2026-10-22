"""CropBot Flask server. Run on the Pi to expose the dashboard on its Wi-Fi."""
import io, json, logging, os, threading, time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

try:
    import cv2
except ImportError:
    cv2 = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('cropbot')
BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = None
CLASS_NAMES = []
MODEL_ERROR = 'No trained model found in outputs/models.'
LAST_SCAN = None
HARDWARE = None
try:
    from hardware.device import Device
    HARDWARE = Device()
except Exception as exc:
    log.info('GPIO hardware unavailable; safe simulation mode: %s', exc)

DISEASE_GUIDANCE = {
    'healthy': ('No disease pattern detected', 'Continue regular monitoring. Keep foliage dry and maintain good airflow.'),
    'blight': ('Fungal leaf disease', 'Remove badly affected leaves, avoid overhead watering, and ask a local agronomist about locally approved treatment.'),
    'rust': ('Rust-like fungal symptoms', 'Remove infected debris, improve airflow, and confirm the diagnosis before applying any treatment.'),
    'mildew': ('Mildew-like symptoms', 'Improve airflow, avoid wetting leaves, and confirm severity with a local crop specialist.'),
    'spot': ('Leaf spot symptoms', 'Remove affected foliage, keep tools clean, and confirm the cause before treatment.'),
    'virus': ('Possible viral symptoms', 'Isolate affected plants and control insect vectors; seek local expert confirmation.'),
    'scab': ('Scab-like symptoms', 'Remove infected debris and avoid overhead watering; confirm before treatment.'),
    'rot': ('Rot-like symptoms', 'Remove affected material and check drainage; confirm cause before treatment.'),
}

def load_model():
    global MODEL, CLASS_NAMES, MODEL_ERROR
    mapping = os.path.join(BASE, 'models', 'class_indices.json')
    if os.path.exists(mapping):
        with open(mapping, encoding='utf-8') as f:
            data = json.load(f)
        CLASS_NAMES = [data[str(i)] for i in range(len(data))]
    model_path = os.path.join(BASE, 'models', 'plant_disease_model.keras')
    if not os.path.exists(model_path):
        model_path = os.path.join(BASE, 'models', 'plant_disease_model.h5')
    if not os.path.exists(mapping):
        MODEL_ERROR = 'Missing models/class_indices.json. Train a model and copy its class list into models/.'
        return
    if os.path.exists(model_path):
        import tensorflow as tf
        MODEL = tf.keras.models.load_model(model_path)
        if len(CLASS_NAMES) != int(MODEL.output_shape[-1]):
            MODEL = None
            MODEL_ERROR = 'The class list and model output size do not match. Copy both files from the same training run.'
            return
        MODEL_ERROR = ''
        log.info('Loaded model from %s', model_path)
    else:
        MODEL_ERROR = 'Missing models/plant_disease_model.keras (or .h5). Train a model and copy it into models/.'

def analyze(image_bytes):
    global LAST_SCAN
    if MODEL is None or not CLASS_NAMES:
        raise RuntimeError(MODEL_ERROR or 'No trained model is loaded. Check models/ and restart Flask.')
    import numpy as np
    from PIL import Image
    image = Image.open(io.BytesIO(image_bytes)).convert('RGB').resize((224, 224))
    x = np.asarray(image, dtype=np.float32)[None, ...]
    pred = MODEL.predict(x, verbose=0)[0]
    indices = np.argsort(pred)[::-1][:3]
    rows = []
    for i in indices:
        label = CLASS_NAMES[int(i)]
        plant, disease = (label.split('___', 1) + ['Unknown'])[:2]
        low = disease.lower()
        title, advice = next((v for k, v in DISEASE_GUIDANCE.items() if k in low),
                             ('Check the leaf closely', 'This model result is a screening aid. Retake a clear image and confirm with a local crop specialist.'))
        rows.append({'class_name': label, 'plant': plant.replace('_', ' '), 'disease': disease.replace('_', ' '),
                     'confidence': round(float(pred[i]) * 100, 1), 'summary': title, 'solution': advice})
    LAST_SCAN = {'timestamp': datetime.now().astimezone().isoformat(), 'result': rows[0]}
    return rows

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/status')
def status():
    return jsonify({'model_ready': MODEL is not None, 'model_error': MODEL_ERROR,
                    'opencv_available': cv2 is not None, 'hardware_connected': HARDWARE is not None,
                    'timestamp': datetime.now().astimezone().isoformat()})

@app.post('/api/scan')
def scan():
    image = request.files.get('image')
    if image is None:
        return jsonify(error='Attach a leaf image using the image field.'), 400
    try: return jsonify(predictions=analyze(image.read()))
    except RuntimeError as e: return jsonify(error=str(e)), 503
    except Exception as e:
        log.exception('Scan failed')
        return jsonify(error='Could not read or classify that image.'), 400

@app.post('/api/camera-scan')
def camera_scan():
    if cv2 is None: return jsonify(error='OpenCV is not installed on the Pi.'), 503
    camera_id = request.json.get('camera_id', 0) if request.is_json else 0
    try: camera_id = int(camera_id)
    except (TypeError, ValueError): return jsonify(error='camera_id must be 0 or 1.'), 400
    if camera_id not in (0, 1): return jsonify(error='camera_id must be 0 or 1.'), 400
    cap = cv2.VideoCapture(camera_id)
    try:
        if not cap.isOpened(): return jsonify(error=f'Pi camera {camera_id} is unavailable.'), 503
        ok, frame = cap.read()
        if not ok: return jsonify(error='Camera did not return a frame.'), 503
        ok, data = cv2.imencode('.jpg', frame)
        if not ok: return jsonify(error='Could not encode camera frame.'), 500
        return jsonify(predictions=analyze(data.tobytes()))
    except RuntimeError as e: return jsonify(error=str(e)), 503
    finally: cap.release()

@app.get('/api/sensors')
def sensors():
    return jsonify(HARDWARE.read_sensors() if HARDWARE else {'simulated': True, 'soil_dry': None, 'rain_detected': None, 'pump_on': False})

@app.post('/api/pump')
def pump():
    data = request.get_json(silent=True) or {}
    if data.get('action') not in ('on', 'off'): return jsonify(error='action must be on or off'), 400
    seconds = min(max(int(data.get('seconds', 3)), 1), 10)
    if HARDWARE:
        if data['action'] == 'on': HARDWARE.pump_for(seconds)
        else: HARDWARE.pump_off()
    return jsonify(status='ok', action=data['action'], seconds=seconds, simulated=HARDWARE is None)

@app.post('/api/motor')
def motor():
    data = request.get_json(silent=True) or {}
    direction = data.get('direction', 'stop')
    if direction not in ('forward', 'backward', 'left', 'right', 'stop'):
        return jsonify(error='Unknown direction'), 400
    if HARDWARE:
        return jsonify(error='Motor control is disabled until direction and enable pins are configured.'), 501
    return jsonify(status='ok', direction=direction, simulated=True)

@app.get('/api/history')
def history(): return jsonify([LAST_SCAN] if LAST_SCAN else [])

if __name__ == '__main__':
    try: load_model()
    except Exception: log.exception('Model loading failed; scan API will report unavailable')
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=False, threaded=True)
else:
    # Gunicorn/Cloud Run imports app:app instead of running this file directly.
    try: load_model()
    except Exception:
        MODEL_ERROR = 'Model could not be loaded. Check TensorFlow and the model files.'
        log.exception('Model loading failed; scan API will report unavailable')

