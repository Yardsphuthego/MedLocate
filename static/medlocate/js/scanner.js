/* Native barcode scanning with a manual entry fallback; no captured media leaves the device. */
window.medlocateInitScanner = (root = document) => root.querySelectorAll('[data-scanner]:not([data-scanner-ready])').forEach(panel => {
  panel.dataset.scannerReady = 'true';
  const video = panel.querySelector('[data-camera]');
  const status = panel.querySelector('[data-camera-status]');
  const start = panel.querySelector('[data-start-camera]');
  const stopButton = panel.querySelector('[data-stop-camera]');
  let stream, running = false, timer, generation = 0;
  const stop = () => {
    generation++; running = false; clearTimeout(timer);
    stream?.getTracks().forEach(track => track.stop()); stream = null;
    video.srcObject = null; video.hidden = true; stopButton.hidden = true; start.disabled = false;
  };
  stopButton.addEventListener('click', () => { stop(); status.textContent = 'Camera stopped. You can enter the code manually.'; });
  window.addEventListener('pagehide', stop);
  document.addEventListener('medlocate:beforevisit', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  start.addEventListener('click', async () => {
    if (!window.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Camera scanning is not supported in this browser. Type the barcode, medicine name or prescription reference manually.'; return;
    }
    start.disabled = true;
    status.textContent = "Requesting camera access…";
    const version = ++generation;
    try {
      const supported = await BarcodeDetector.getSupportedFormats();
      const wanted = panel.dataset.formats === 'qr' ? ['qr_code'] : ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'data_matrix'];
      const formats = wanted.filter(f => supported.includes(f));
      if (!formats.length) throw new Error('Unsupported format');
      const detector = new BarcodeDetector({ formats });
      const acquired = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      if (version !== generation) { acquired.getTracks().forEach(t => t.stop()); return; }
      stream = acquired; video.srcObject = stream; video.hidden = false; stopButton.hidden = false;
      await video.play(); running = true; status.textContent = 'Hold the code steady inside the camera view.';
      const detect = async () => {
        if (!running || version !== generation) return;
        try {
          const codes = await detector.detect(video);
          if (!running || version !== generation) return;
          if (codes.length) {
            document.getElementById(panel.dataset.target).value = codes[0].rawValue;
            stop(); status.textContent = 'Code captured. Check it, then submit to review the match.'; return;
          }
          timer = setTimeout(detect, 250);
        } catch { stop(); status.textContent = 'Could not read the code. Try again or enter it manually.'; }
      };
      detect();
    } catch { stop(); status.textContent = 'Camera unavailable or permission denied. Enter the code manually.'; }
  });
});
document.addEventListener('DOMContentLoaded', () => window.medlocateInitScanner());
document.addEventListener('medlocate:contentloaded', () => window.medlocateInitScanner());
