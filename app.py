"""CropBot: software-only plant disease screening website and API."""
import io
import json
import logging
import os
from datetime import datetime, timezone

import numpy as np
from flask import Flask, jsonify, render_template, request
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('cropbot')
BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = None
CLASS_NAMES = []
MODEL_ERROR = 'The disease model is not available.'

# Guidance is deliberately focused on observation, sanitation, and growing
# conditions. Confirm diagnoses locally before using crop protection products.
GUIDANCE = {
    'healthy': {
        'summary': 'No disease pattern detected', 'severity': 'Looks healthy',
        'solution': 'No disease-like pattern was detected in this image. Continue routine monitoring and compare new leaves over time.',
        'actions': ['Keep checking both sides of leaves as the plant grows.', 'Water near the soil and avoid keeping foliage wet for long periods.'],
        'prevention': 'Maintain steady watering, good airflow, and clean growing areas.'},
    'bacterial_spot': {
        'summary': 'Possible bacterial leaf spot', 'severity': 'Monitor closely',
        'solution': 'The image resembles bacterial spot. Remove badly affected leaves when plants are dry and avoid handling plants while wet.',
        'actions': ['Keep tools clean between plants.', 'Avoid overhead watering and reduce leaf-to-leaf splashing.', 'If symptoms keep spreading, confirm with a local agricultural extension service.'],
        'prevention': 'Use clean seed or transplants, rotate crops where practical, and clear infected plant debris.'},
    'early_blight': {
        'summary': 'Possible early blight', 'severity': 'Treat as a warning',
        'solution': 'The image resembles early blight. Remove heavily affected lower leaves and keep healthy foliage as dry as practical.',
        'actions': ['Water at the base of the plant.', 'Remove fallen leaves from around the plant.', 'Improve spacing and airflow; confirm the diagnosis if it progresses.'],
        'prevention': 'Rotate crop locations where practical and avoid leaving infected debris in the bed.'},
    'late_blight': {
        'summary': 'Possible late blight', 'severity': 'Check promptly',
        'solution': 'Late blight can spread quickly. Keep the plant separate if possible and get a prompt local confirmation, especially if symptoms are expanding.',
        'actions': ['Avoid touching other plants after handling this one.', 'Do not compost suspect infected material.', 'Ask a local agricultural extension service for next steps.'],
        'prevention': 'Use healthy planting material, allow airflow, and monitor during cool, wet weather.'},
    'leaf_mold': {
        'summary': 'Possible leaf mold', 'severity': 'Monitor closely',
        'solution': 'The image resembles leaf mold. Increase airflow around the plant and avoid wetting leaves during watering.',
        'actions': ['Remove severely affected leaves when dry.', 'Reduce crowding and excess humidity around foliage.', 'Check nearby plants for similar changes.'],
        'prevention': 'Keep foliage dry where possible and provide good spacing and ventilation.'},
    'septoria_leaf_spot': {
        'summary': 'Possible Septoria leaf spot', 'severity': 'Monitor closely',
        'solution': 'The image resembles Septoria leaf spot. Remove affected lower leaves and limit soil splash onto foliage.',
        'actions': ['Clear fallen leaves around the plant.', 'Water at the soil line.', 'Clean tools after pruning and monitor new growth.'],
        'prevention': 'Mulch bare soil, rotate crops where practical, and avoid working with wet plants.'},
    'spider_mites': {
        'summary': 'Possible spider mite damage', 'severity': 'Inspect leaf undersides',
        'solution': 'The image may show mite damage. Inspect leaf undersides closely for tiny mites or fine webbing before taking action.',
        'actions': ['Check several leaves, including nearby plants.', 'Rinse foliage gently if appropriate for the crop and conditions.', 'Seek local advice if pests are widespread.'],
        'prevention': 'Monitor during hot, dry periods and reduce dust and plant stress.'},
    'target_spot': {
        'summary': 'Possible target spot', 'severity': 'Monitor closely',
        'solution': 'The image resembles target spot. Remove badly affected leaves when dry and improve airflow around the plant.',
        'actions': ['Avoid overhead irrigation.', 'Remove plant debris and clean tools.', 'Confirm the cause if spots continue to spread.'],
        'prevention': 'Use good spacing, keep foliage dry, and rotate crop locations where possible.'},
    'yellow_leaf_curl': {
        'summary': 'Possible viral leaf-curl symptoms', 'severity': 'Check promptly',
        'solution': 'Leaf curl can have several causes, including viruses and environmental stress. Inspect the plant and nearby plants, and seek local confirmation.',
        'actions': ['Check leaf undersides for whiteflies or other pests.', 'Avoid taking cuttings from a suspect plant.', 'Ask a local crop specialist how to handle confirmed virus symptoms.'],
        'prevention': 'Use healthy transplants and monitor for insect vectors and weeds around the crop.'},
    'mosaic_virus': {
        'summary': 'Possible mosaic virus symptoms', 'severity': 'Check promptly',
        'solution': 'Mosaic-like patterns can have several causes. Isolate the plant where possible and confirm the diagnosis locally; there is no general image-based cure.',
        'actions': ['Clean hands and tools before moving between plants.', 'Avoid using suspect plants for propagation.', 'Ask a local crop specialist about confirmed cases.'],
        'prevention': 'Use clean planting material, control weeds and vectors, and sanitize tools between plants.'},
    'powdery_mildew': {
        'summary': 'Possible powdery mildew', 'severity': 'Monitor closely',
        'solution': 'The image resembles powdery mildew. Improve airflow and monitor whether the powdery patches spread to new leaves.',
        'actions': ['Avoid crowding plants.', 'Remove severely affected leaves when dry.', 'Confirm the cause before using any treatment.'],
        'prevention': 'Choose suitable spacing and avoid excessive shade and stagnant air.'},
    'apple_scab': {
        'summary': 'Possible apple scab', 'severity': 'Monitor new growth',
        'solution': 'The image resembles apple scab. Remove fallen affected leaves and keep the canopy open so foliage dries more quickly.',
        'actions': ['Avoid overhead watering.', 'Clear infected leaf debris from under the tree.', 'Ask a local orchard specialist before applying any crop treatment.'],
        'prevention': 'Maintain airflow and remove infected fallen leaves as part of seasonal orchard cleanup.'},
    'apple_rust': {
        'summary': 'Possible apple rust symptoms', 'severity': 'Confirm locally',
        'solution': 'The image may show rust-like spots. Check several leaves and fruit, then confirm the cause with a local extension service before treating.',
        'actions': ['Remove badly affected fallen leaves.', 'Photograph new symptoms and check whether they spread.', 'Avoid applying a treatment based on one image alone.'],
        'prevention': 'Monitor during wet spring weather and keep notes on symptom timing and nearby host plants.'},
    'gray_leaf_spot': {
        'summary': 'Possible gray leaf spot', 'severity': 'Monitor crop spread',
        'solution': 'The image resembles gray leaf spot. Reduce leaf wetness and confirm the diagnosis with a local crop adviser, especially if lesions are spreading.',
        'actions': ['Avoid working through wet foliage.', 'Manage crop residue and rotation using local extension guidance.', 'Check nearby leaves for similar lesions.'],
        'prevention': 'Use locally recommended crop rotation and residue management, and scout regularly in humid weather.'},
    'leaf_blight': {
        'summary': 'Possible leaf blight', 'severity': 'Confirm the cause',
        'solution': 'The image shows a blight-like pattern, but several diseases and environmental stresses can look similar. Seek a local crop diagnosis before treatment.',
        'actions': ['Remove badly affected leaves when dry if practical.', 'Keep foliage dry and improve airflow.', 'Check nearby plants and record how quickly symptoms change.'],
        'prevention': 'Use clean planting material, crop-specific rotation advice, and regular scouting.'},
    'corn_rust': {
        'summary': 'Possible corn rust', 'severity': 'Monitor promptly',
        'solution': 'The image resembles rust pustules. Check several leaves and ask a local crop adviser whether the symptoms and timing match rust in your area.',
        'actions': ['Photograph both sides of affected leaves.', 'Scout nearby plants for new pustules.', 'Follow local extension recommendations before choosing a control measure.'],
        'prevention': 'Use locally adapted varieties and scout during weather favorable to foliar disease.'},
    'black_rot': {
        'summary': 'Possible grape black rot', 'severity': 'Monitor fruit and leaves',
        'solution': 'The image resembles grape black rot. Remove mummified berries and infected plant debris, and improve canopy airflow.',
        'actions': ['Do not leave infected berries on the vine or ground.', 'Prune for airflow when appropriate for the season.', 'Confirm the diagnosis and any treatment timing with a local viticulture adviser.'],
        'prevention': 'Keep the canopy open and remove infected fruit and debris during regular vineyard sanitation.'},
    'unknown': {
        'summary': 'Possible leaf-health issue', 'severity': 'Confirm the result',
        'solution': 'The model recognizes a visual class, but CropBot has no crop-specific care guidance for this class. A photo alone cannot confirm a disease.',
        'actions': ['Inspect several leaves and the whole plant for similar symptoms.', 'Compare with a trusted local crop guide or ask an agricultural extension specialist before treating.'],
        'prevention': 'Keep notes on symptom changes, watering, and recent weather while you confirm the cause.'},
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def load_model():
    """Load the trained model and matching class-index file from models/."""
    global MODEL, CLASS_NAMES, MODEL_ERROR
    model_path = os.path.join(BASE, 'models', 'plant_disease_model.keras')
    class_path = os.path.join(BASE, 'models', 'class_indices.json')
    try:
        with open(class_path, encoding='utf-8') as file:
            mapping = json.load(file)
        names = [mapping[str(i)] for i in range(len(mapping))]
        import tensorflow as tf
        model = tf.keras.models.load_model(model_path)
        if len(names) != int(model.output_shape[-1]):
            raise ValueError('Model output and class list do not match.')
        MODEL, CLASS_NAMES, MODEL_ERROR = model, names, ''
        log.info('Loaded disease classifier with %s classes.', len(names))
    except Exception as exc:
        MODEL, CLASS_NAMES = None, []
        MODEL_ERROR = 'Model could not load. Check the model files and service memory.'
        log.exception('Model startup failed: %s', exc)

def details_for(label):
    crop, disease = (label.split('___', 1) + ['Unknown'])[:2]
    plant = ' '.join(crop.replace('_', ' ').split()).title()
    if disease.lower().startswith(crop.lower() + '_'):
        disease = disease[len(crop) + 1:]
    disease_key = disease.lower().replace(' ', '_')
    if disease_key == 'healthy':
        key = 'healthy'
    elif 'bacterial_spot' in disease_key:
        key = 'bacterial_spot'
    elif 'early_blight' in disease_key:
        key = 'early_blight'
    elif 'late_blight' in disease_key:
        key = 'late_blight'
    elif 'leaf_mold' in disease_key:
        key = 'leaf_mold'
    elif 'septoria' in disease_key:
        key = 'septoria_leaf_spot'
    elif 'spider_mite' in disease_key:
        key = 'spider_mites'
    elif 'target_spot' in disease_key:
        key = 'target_spot'
    elif 'yellowleaf' in disease_key or 'yellow_leaf' in disease_key:
        key = 'yellow_leaf_curl'
    elif 'mosaic' in disease_key:
        key = 'mosaic_virus'
    elif 'powdery_mildew' in disease_key:
        key = 'powdery_mildew'
    elif 'scab' in disease_key and plant.lower() == 'apple':
        key = 'apple_scab'
    elif 'rust' in disease_key and plant.lower() == 'apple':
        key = 'apple_rust'
    elif 'gray_leaf_spot' in disease_key:
        key = 'gray_leaf_spot'
    elif 'leaf_blight' in disease_key:
        key = 'leaf_blight'
    elif 'rust' in disease_key and plant.lower() == 'corn':
        key = 'corn_rust'
    elif 'black_rot' in disease_key:
        key = 'black_rot'
    else:
        key = 'unknown'
    info = GUIDANCE[key]
    return {
        'class_name': label,
        'plant': plant,
        'disease': 'Healthy' if key == 'healthy' else ' '.join(disease.replace('_', ' ').split()).title(),
        'summary': info['summary'],
        'severity': info['severity'],
        'solution': info['solution'],
        'actions': info['actions'],
        'prevention': info['prevention'],
    }

def analyze(image_bytes):
    if MODEL is None or not CLASS_NAMES:
        raise RuntimeError(MODEL_ERROR or 'The disease model is not loaded.')
    image = Image.open(io.BytesIO(image_bytes)).convert('RGB').resize((224, 224))
    pixels = np.asarray(image, dtype=np.float32)[None, ...]
    probabilities = MODEL.predict(pixels, verbose=0)[0]
    # Sum disease-class probabilities by crop so the plant name is less
    # sensitive to confusion between two diseases of the same plant.
    crop_probabilities = {}
    for index, label in enumerate(CLASS_NAMES):
        crop = label.split('___', 1)[0]
        crop_probabilities[crop] = crop_probabilities.get(crop, 0.0) + float(probabilities[index])
    best_crop = max(crop_probabilities, key=crop_probabilities.get)
    indices = sorted(range(len(probabilities)), key=lambda i: probabilities[i], reverse=True)
    best_crop_index = next(i for i in indices if CLASS_NAMES[i].split('___', 1)[0] == best_crop)
    indices = [best_crop_index] + [i for i in indices if i != best_crop_index][:2]
    results = []
    for index in indices:
        row = details_for(CLASS_NAMES[int(index)])
        row['confidence'] = round(float(probabilities[index]) * 100, 1)
        row['plant_confidence'] = round(crop_probabilities[row['class_name'].split('___', 1)[0]] * 100, 1)
        results.append(row)
    return results

@app.get('/')
def home():
    return render_template('index.html', page='home')

@app.get('/scanner')
def scanner():
    return render_template('scanner.html', page='scanner')

@app.get('/guide')
def guide():
    return render_template('guide.html', page='guide')

@app.get('/journal')
def journal():
    return render_template('journal.html', page='journal')

@app.get('/healthz')
def healthz():
    return jsonify(status='ok')

@app.get('/api/status')
def status():
    supported_crops = sorted({
        ' '.join(label.split('___', 1)[0].replace('__', '_').replace('_', ' ').split()).title()
        for label in CLASS_NAMES
    })
    return jsonify(model_ready=MODEL is not None, model_error=MODEL_ERROR,
                   supported_classes=len(CLASS_NAMES), supported_crops=supported_crops)

@app.get('/api/diseases')
def diseases():
    return jsonify([details_for(label) for label in CLASS_NAMES])

@app.post('/api/scan')
def scan():
    upload = request.files.get('image')
    if upload is None or not upload.filename:
        return jsonify(error='Choose a leaf photo first.'), 400
    try:
        image_data = upload.read()
        with Image.open(io.BytesIO(image_data)) as image:
            image.verify()
        predictions = analyze(image_data)
        return jsonify(predictions=predictions, scanned_at=utc_now())
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify(error='That image could not be read. Choose a JPG, PNG, or WEBP photo.'), 400
    except Exception:
        log.exception('Leaf scan failed.')
        return jsonify(error='The scan could not be completed. Try a clear, well-lit leaf photo.'), 500

@app.errorhandler(413)
def too_large(_error):
    return jsonify(error='Photo is too large. Please choose an image under 12 MB.'), 413

if __name__ != '__main__':
    load_model()
elif os.environ.get('CROPBOT_LOAD_MODEL', '1') == '1':
    load_model()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=False)
