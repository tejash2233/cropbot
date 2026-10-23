const $ = (selector, root = document) => root.querySelector(selector);
const JOURNAL_KEY = 'cropbot-journal-v1';
let cameraStream = null;
let cameraFacing = 'environment';
let scanPhoto = null;
let previewUrl = null;

function toast(message) {
  const node = $('#toast');
  if (!node) return;
  node.textContent = message;
  node.classList.add('show');
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove('show'), 3000);
}

function readJournal() {
  try {
    const value = JSON.parse(localStorage.getItem(JOURNAL_KEY) || '[]');
    return Array.isArray(value) ? value : [];
  } catch (_) { return []; }
}

function writeJournal(items) {
  try { localStorage.setItem(JOURNAL_KEY, JSON.stringify(items.slice(0, 100))); return true; }
  catch (_) { toast('Browser storage is full. Export or clear older notes.'); return false; }
}

function addJournalEntry(predictions, scannedAt) {
  const entry = { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, scannedAt,
    result: predictions[0], alternatives: predictions.slice(1) };
  const items = readJournal();
  items.unshift(entry);
  writeJournal(items);
  updateNavCount();
}

function updateNavCount() {
  const count = $('#navCount');
  if (count) count.textContent = String(readJournal().length);
}

function makeNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function getStatus() {
  try {
    const response = await fetch('/api/status');
    const status = await response.json();
    const homeStatus = $('#homeModelStatus');
    const count = $('#classCount');
    if (count && status.supported_classes) count.textContent = status.supported_classes;
    const coverage = $('.supported-chip small');
    if (coverage && Array.isArray(status.supported_crops) && status.supported_crops.length) {
      coverage.textContent = status.supported_crops.join(' · ');
    }
    const patternCount = $('.supported-chip strong');
    if (patternCount && status.supported_classes) patternCount.textContent = `${status.supported_classes} crop / disease labels`;
    if (homeStatus) homeStatus.textContent = status.model_ready ? `AI model online · ${status.supported_classes} leaf patterns` : 'AI model unavailable · check deployment logs';
    const message = $('#scanMessage');
    const button = $('#analyzePhoto');
    if (message && !status.model_ready) message.textContent = status.model_error || 'The model is not ready. Please try again later.';
    if (button && !status.model_ready) button.disabled = true;
  } catch (_) {
    const homeStatus = $('#homeModelStatus');
    if (homeStatus) homeStatus.textContent = 'Could not reach the AI service';
  }
}

function stopCamera() {
  if (cameraStream) cameraStream.getTracks().forEach(track => track.stop());
  cameraStream = null;
}

function clearPreviewUrl() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
}

function setPreview(blob, label) {
  clearPreviewUrl();
  previewUrl = URL.createObjectURL(blob);
  $('#photoPreview').src = previewUrl;
  $('#photoPreview').hidden = false;
  $('#cameraVideo').hidden = true;
  $('#mediaEmpty').hidden = true;
  $('#cameraState').innerHTML = `<i></i> ${label}`;
  $('#analyzePhoto').disabled = false;
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    $('#scanMessage').textContent = 'Camera access needs HTTPS or localhost. Use Choose a photo if the camera cannot open.';
    return;
  }
  stopCamera();
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: cameraFacing } }, audio: false });
    const video = $('#cameraVideo');
    video.srcObject = cameraStream;
    video.hidden = false;
    $('#photoPreview').hidden = true;
    $('#mediaEmpty').hidden = true;
    $('#cameraState').innerHTML = '<i></i> LIVE CAMERA';
    $('#enableCamera').innerHTML = '<span>◉</span> Camera on';
    $('#captureFrame').disabled = false;
    $('#switchCamera').disabled = false;
    $('#analyzePhoto').disabled = true;
    scanPhoto = null;
    $('#scanMessage').textContent = 'Center one clear leaf in the frame, then capture it.';
    await video.play();
  } catch (error) {
    $('#scanMessage').textContent = 'Camera could not open. Allow camera permission or choose a photo instead.';
    toast(error.name === 'NotAllowedError' ? 'Allow camera access in your browser settings.' : 'Could not open a camera on this device.');
  }
}

function captureFrame() {
  const video = $('#cameraVideo');
  if (!cameraStream || !video.videoWidth) {
    $('#scanMessage').textContent = 'Wait for the camera image, then try capturing again.';
    return;
  }
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(blob => {
    if (!blob) { toast('Could not capture this frame.'); return; }
    scanPhoto = blob;
    stopCamera();
    $('#enableCamera').innerHTML = '<span>◉</span> Retake photo';
    $('#captureFrame').disabled = true;
    $('#switchCamera').disabled = true;
    setPreview(blob, 'PHOTO READY');
    $('#scanMessage').textContent = 'Photo captured. Review it, then analyze the leaf.';
  }, 'image/jpeg', 0.92);
}

function renderResult(predictions) {
  const container = $('#scanResult');
  const empty = $('#resultEmpty');
  container.replaceChildren();
  empty.hidden = true;
  container.hidden = false;
  const best = predictions[0];
  const main = makeNode('article', 'diagnosis-card');
  const plantMatch = best.plant_confidence ? ` · plant match ${best.plant_confidence}%` : '';
  main.append(makeNode('div', 'diagnosis-topline', `${best.plant}${plantMatch}  /  ${best.severity}`));
  main.append(makeNode('h3', 'diagnosis-title', best.disease));
  main.append(makeNode('p', 'diagnosis-summary', best.summary));
  const confidence = makeNode('div', 'confidence-label');
  confidence.append(makeNode('span', '', 'Model match'), makeNode('strong', '', `${best.confidence}%`));
  main.append(confidence);
  const bar = makeNode('div', 'confidence-track');
  const fill = makeNode('i');
  fill.style.width = `${Math.max(2, Math.min(100, best.confidence))}%`;
  bar.append(fill); main.append(bar);
  if (best.confidence < 55) main.append(makeNode('p', 'uncertain-note', 'The model is unsure. Try a closer, brighter photo of one supported crop leaf.'));
  main.append(makeNode('h4', 'result-subhead', 'A helpful next step'));
  main.append(makeNode('p', 'solution-copy', best.solution));
  main.append(makeNode('h4', 'result-subhead', 'What you can do'));
  const actions = makeNode('ul', 'care-list');
  (best.actions || []).forEach(item => actions.append(makeNode('li', '', item)));
  main.append(actions);
  main.append(makeNode('h4', 'result-subhead', 'Prevention note'));
  main.append(makeNode('p', 'solution-copy', best.prevention));
  if (predictions.length > 1) {
    const alternatives = makeNode('details', 'alternatives');
    alternatives.append(makeNode('summary', '', 'See other possible matches'));
    predictions.slice(1).forEach(item => {
      const row = makeNode('div', 'alternative-row');
      row.append(makeNode('span', '', `${item.plant} · ${item.disease}`), makeNode('strong', '', `${item.confidence}%`));
      alternatives.append(row);
    });
    main.append(alternatives);
  }
  const buttons = makeNode('div', 'result-actions');
  const copy = makeNode('button', 'button button-outline', 'Copy summary');
  copy.type = 'button';
  copy.onclick = async () => {
    const text = `${best.plant} — ${best.disease}\n${best.summary}\nModel match: ${best.confidence}%\nNext step: ${best.solution}\nAI screening only; confirm uncertain results locally.`;
    try { await navigator.clipboard.writeText(text); toast('Summary copied.'); }
    catch (_) { toast('Clipboard is not available in this browser.'); }
  };
  buttons.append(copy, makeNode('a', 'text-link', 'View journal →'));
  buttons.lastChild.href = '/journal';
  main.append(buttons);
  container.append(main);
}

async function analyzePhoto() {
  if (!scanPhoto) { toast('Capture a leaf or choose a photo first.'); return; }
  const button = $('#analyzePhoto');
  button.disabled = true;
  button.textContent = 'Reading your leaf…';
  $('#scanMessage').textContent = 'Looking for visual patterns. This may take a few moments on the first scan.';
  try {
    const form = new FormData();
    form.append('image', scanPhoto, 'leaf.jpg');
    const response = await fetch('/api/scan', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Scan could not be completed.');
    renderResult(data.predictions);
    addJournalEntry(data.predictions, data.scanned_at || new Date().toISOString());
    $('#scanMessage').textContent = 'Scan complete. Your result has been added to this browser’s journal.';
    toast('Leaf scan complete.');
  } catch (error) {
    $('#scanMessage').textContent = error.message;
    toast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Analyze leaf <span>→</span>';
    if (!scanPhoto) button.disabled = true;
  }
}

function setupScanner() {
  const input = $('#imageInput');
  if (!input) return;
  $('#enableCamera').addEventListener('click', () => startCamera());
  $('#switchCamera').addEventListener('click', async () => {
    cameraFacing = cameraFacing === 'environment' ? 'user' : 'environment';
    await startCamera();
  });
  $('#captureFrame').addEventListener('click', captureFrame);
  $('#analyzePhoto').addEventListener('click', analyzePhoto);
  input.addEventListener('change', event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) { toast('Choose an image file.'); return; }
    stopCamera();
    scanPhoto = file;
    $('#enableCamera').innerHTML = '<span>◉</span> Use camera';
    $('#captureFrame').disabled = true;
    $('#switchCamera').disabled = true;
    setPreview(file, 'PHOTO READY');
    $('#scanMessage').textContent = `${file.name} is ready to analyze.`;
  });
  window.addEventListener('pagehide', stopCamera);
}

function setupGuide() {
  const grid = $('#guideGrid');
  if (!grid) return;
  const filterBar = $('#cropFilters');
  let all = [];
  let crop = 'all';
  const search = $('#guideSearch');
  function paint() {
    const query = search.value.trim().toLowerCase();
    const rows = all.filter(row => (crop === 'all' || row.plant.toLowerCase().includes(crop)) &&
      (!query || `${row.plant} ${row.disease} ${row.summary}`.toLowerCase().includes(query)));
    grid.replaceChildren();
    if (!rows.length) { grid.append(makeNode('p', 'guide-loading', 'No matches. Try another crop or search.')); return; }
    rows.forEach(row => {
      const card = makeNode('article', 'guide-card');
      const top = makeNode('div', 'guide-card-top');
      top.append(makeNode('span', 'crop-tag', row.plant), makeNode('span', `severity-tag ${row.disease === 'Healthy' ? 'is-healthy' : ''}`, row.severity));
      card.append(top, makeNode('h3', '', row.disease), makeNode('p', 'guide-summary', row.summary));
      const disclosure = makeNode('details', 'guide-details');
      disclosure.append(makeNode('summary', '', 'Care suggestions'));
      disclosure.append(makeNode('p', '', row.solution));
      const list = makeNode('ul', 'care-list');
      (row.actions || []).forEach(action => list.append(makeNode('li', '', action)));
      disclosure.append(list, makeNode('p', 'prevention-copy', `Prevention · ${row.prevention}`));
      card.append(disclosure);
      grid.append(card);
    });
  }
  search.addEventListener('input', paint);
  fetch('/api/diseases').then(response => response.json()).then(rows => {
    all = rows;
    const crops = [...new Set(all.map(row => row.plant))].sort((a, b) => a.localeCompare(b));
    const buttons = [makeNode('button', 'filter-pill active', 'All crops'), ...crops.map(name => makeNode('button', 'filter-pill', name))];
    buttons.forEach((button, index) => {
      button.type = 'button';
      button.dataset.crop = index === 0 ? 'all' : button.textContent.toLowerCase();
      button.addEventListener('click', () => {
        crop = button.dataset.crop;
        buttons.forEach(item => item.classList.toggle('active', item === button));
        paint();
      });
    });
    if (filterBar) filterBar.replaceChildren(...buttons);
    const stamp = $('#guideStampCount');
    if (stamp) stamp.textContent = `${all.length} LABELS`;
    paint();
  })
    .catch(() => { grid.replaceChildren(makeNode('p', 'guide-loading', 'The field guide could not load. Refresh the page to try again.')); });
}

function formatDate(dateString, includeTime = true) {
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return new Intl.DateTimeFormat(undefined, includeTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(date);
}

function setupJournal() {
  const list = $('#journalList');
  if (!list) return;
  const filter = $('#journalFilter');
  function paint() {
    const items = readJournal();
    $('#journalTotal').textContent = String(items.length);
    $('#journalPlants').textContent = String(new Set(items.map(item => item.result?.plant).filter(Boolean)).size);
    $('#journalLatest').textContent = items[0]?.result?.plant || '—';
    $('#journalLatestTime').textContent = items[0] ? formatDate(items[0].scannedAt) : 'Scan a leaf to begin';
    const showing = items.filter(item => {
      const healthy = item.result?.disease?.toLowerCase() === 'healthy';
      return filter.value === 'all' || (filter.value === 'healthy' ? healthy : !healthy);
    });
    list.replaceChildren();
    $('#journalEmpty').hidden = items.length > 0;
    if (!items.length) return;
    if (!showing.length) { list.append(makeNode('p', 'guide-loading', 'No scans in this filter yet.')); return; }
    showing.forEach((item, index) => {
      const card = makeNode('article', 'journal-entry');
      const icon = makeNode('div', 'journal-entry-icon', item.result?.disease?.toLowerCase() === 'healthy' ? '✓' : '✳');
      const main = makeNode('div', 'journal-entry-main');
      main.append(makeNode('span', 'entry-date', formatDate(item.scannedAt)), makeNode('h3', '', `${item.result?.plant || 'Plant'} · ${item.result?.disease || 'Scan'}`), makeNode('p', '', item.result?.summary || 'Plant health observation'));
      const confidence = makeNode('div', 'entry-confidence');
      confidence.append(makeNode('strong', '', `${item.result?.confidence ?? '—'}%`), makeNode('span', '', 'model match'));
      const details = makeNode('details', 'entry-details');
      details.append(makeNode('summary', '', 'Care notes'));
      details.append(makeNode('p', '', item.result?.solution || 'No care note available.'));
      const actions = makeNode('ul', 'care-list');
      (item.result?.actions || []).forEach(action => actions.append(makeNode('li', '', action)));
      details.append(actions);
      card.append(icon, main, confidence, details, makeNode('span', 'entry-index', String(items.length - index).padStart(2, '0')));
      list.append(card);
    });
  }
  filter.addEventListener('change', paint);
  $('#clearJournal').addEventListener('click', () => {
    if (!readJournal().length) return;
    if (window.confirm('Clear all scan notes saved in this browser? This cannot be undone.')) {
      localStorage.removeItem(JOURNAL_KEY); updateNavCount(); paint(); toast('Journal cleared.');
    }
  });
  $('#exportJournal').addEventListener('click', () => {
    const items = readJournal();
    if (!items.length) { toast('There are no notes to export yet.'); return; }
    const esc = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
    const lines = [['Date', 'Plant', 'Result', 'Confidence', 'Summary', 'Next step'], ...items.map(item => [item.scannedAt, item.result?.plant, item.result?.disease, item.result?.confidence, item.result?.summary, item.result?.solution])];
    const blob = new Blob([lines.map(row => row.map(esc).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'cropbot-field-journal.csv'; link.click(); URL.revokeObjectURL(url);
  });
  paint();
}

const menuToggle = $('#menuToggle');
if (menuToggle) menuToggle.addEventListener('click', () => {
  const open = menuToggle.getAttribute('aria-expanded') !== 'true';
  menuToggle.setAttribute('aria-expanded', String(open));
  $('#mainNav').classList.toggle('open', open);
});

updateNavCount();
getStatus();
setupScanner();
setupGuide();
setupJournal();
