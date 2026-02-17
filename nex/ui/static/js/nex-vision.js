/**
 * NEX VISION — Real-time camera + YOLO HUD overlay with JARVIS aesthetic.
 */

(() => {
    const CYAN = '#00D9FF';
    const CYAN_DIM = 'rgba(0, 217, 255, 0.3)';
    const CYAN_FILL = 'rgba(0, 217, 255, 0.08)';
    const SEND_INTERVAL = 125; // ~8 FPS capture rate
    const JPEG_QUALITY = 0.6;
    const CAPTURE_W = 640;
    const CAPTURE_H = 480;

    // DOM
    const video = document.getElementById('vision-video');
    const canvas = document.getElementById('vision-canvas');
    const noCameraEl = document.getElementById('vision-no-camera');
    const scanlineEl = document.getElementById('vision-scanline');
    const startBtn = document.getElementById('vision-start-btn');
    const confSlider = document.getElementById('vision-conf-slider');
    const confValueEl = document.getElementById('vision-conf-value');
    const detectionsEl = document.getElementById('vision-detections');

    // Stats elements
    const fpsEl = document.getElementById('vision-fps');
    const inferenceEl = document.getElementById('vision-inference');
    const objectsEl = document.getElementById('vision-objects');
    const confidenceEl = document.getElementById('vision-confidence');

    if (!canvas || !video) return;

    const ctx = canvas.getContext('2d');
    const offscreen = document.createElement('canvas');
    offscreen.width = CAPTURE_W;
    offscreen.height = CAPTURE_H;
    const offCtx = offscreen.getContext('2d');

    // State
    let stream = null;
    let ws = null;
    let active = false;
    let mode = 'detect';
    let confThreshold = 0.25;
    let awaitingResponse = false;
    let sendTimer = null;
    let rafId = null;

    // Latest detections from server
    let currentDetections = [];
    let currentMode = 'detect';

    // Stats tracking
    let frameCount = 0;
    let lastFpsTime = performance.now();
    let currentFps = 0;
    let lastInferenceMs = 0;

    // Scanline animation
    let scanlineY = 0;

    // ─── Camera Control ──────────────────────────

    async function startCamera() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: CAPTURE_W, height: CAPTURE_H, facingMode: 'user' },
                audio: false,
            });
            video.srcObject = stream;
            video.style.display = 'block';
            noCameraEl.style.display = 'none';
            scanlineEl.style.display = 'block';
            startBtn.textContent = 'Stop Camera';
            startBtn.classList.add('active');
            active = true;

            await connectVisionWS();
            startSendLoop();
            startHUDLoop();
        } catch (e) {
            console.error('Camera access denied:', e);
            noCameraEl.querySelector('span').textContent = 'Camera access denied';
        }
    }

    function stopCamera() {
        active = false;

        if (sendTimer) { clearInterval(sendTimer); sendTimer = null; }
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }

        if (stream) {
            stream.getTracks().forEach(t => t.stop());
            stream = null;
        }
        video.srcObject = null;
        video.style.display = 'none';

        if (ws) {
            ws.close();
            ws = null;
        }

        noCameraEl.style.display = 'flex';
        scanlineEl.style.display = 'none';
        startBtn.textContent = 'Start Camera';
        startBtn.classList.remove('active');

        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        currentDetections = [];
        detectionsEl.innerHTML = '';
        fpsEl.textContent = '0';
        inferenceEl.textContent = '0ms';
        objectsEl.textContent = '0';
        confidenceEl.textContent = '0%';
    }

    startBtn.addEventListener('click', () => {
        if (active) stopCamera();
        else startCamera();
    });

    // ─── Vision WebSocket ────────────────────────

    async function connectVisionWS() {
        let token = '';
        try {
            const resp = await fetch(`${location.protocol}//${location.hostname || 'localhost'}:${location.port || 8420}/api/auth/token`);
            const data = await resp.json();
            token = data.token || '';
        } catch { return; }

        const wsUrl = `ws://${location.hostname || 'localhost'}:${location.port || 8420}/ws/vision`;
        try { ws = new WebSocket(wsUrl); } catch { return; }

        ws.onopen = () => {
            ws.send(JSON.stringify({ type: 'auth', token }));
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'vision.result') {
                    handleVisionResult(msg);
                }
            } catch {}
            awaitingResponse = false;
        };

        ws.onclose = () => {
            ws = null;
            awaitingResponse = false;
        };

        ws.onerror = () => { if (ws) ws.close(); };
    }

    function handleVisionResult(msg) {
        currentMode = msg.mode;
        lastInferenceMs = msg.inference_ms || 0;

        if (msg.mode === 'classify') {
            currentDetections = (msg.classifications || []).map(c => ({
                class: c.class,
                confidence: c.confidence,
            }));
        } else {
            currentDetections = msg.detections || [];
        }

        // Update stats
        frameCount++;
        const now = performance.now();
        if (now - lastFpsTime >= 1000) {
            currentFps = frameCount;
            frameCount = 0;
            lastFpsTime = now;
        }

        const objCount = currentDetections.length;
        const avgConf = objCount > 0
            ? currentDetections.reduce((s, d) => s + d.confidence, 0) / objCount
            : 0;

        fpsEl.textContent = currentFps;
        inferenceEl.textContent = lastInferenceMs + 'ms';
        objectsEl.textContent = objCount;
        confidenceEl.textContent = Math.round(avgConf * 100) + '%';

        updateDetectionsList();
    }

    // ─── Frame Sending ───────────────────────────

    function startSendLoop() {
        sendTimer = setInterval(() => {
            if (!active || !ws || ws.readyState !== WebSocket.OPEN || awaitingResponse) return;

            offCtx.drawImage(video, 0, 0, CAPTURE_W, CAPTURE_H);
            const dataUrl = offscreen.toDataURL('image/jpeg', JPEG_QUALITY);
            const b64 = dataUrl.split(',')[1];

            ws.send(JSON.stringify({
                type: 'frame',
                data: b64,
                mode: mode,
                confidence: confThreshold,
            }));
            awaitingResponse = true;

        }, SEND_INTERVAL);
    }

    // ─── HUD Rendering (60 FPS) ──────────────────

    function startHUDLoop() {
        function render() {
            if (!active) return;

            const cw = canvas.parentElement.clientWidth;
            const ch = canvas.parentElement.clientHeight;
            if (canvas.width !== cw || canvas.height !== ch) {
                canvas.width = cw;
                canvas.height = ch;
            }

            ctx.clearRect(0, 0, cw, ch);

            if (currentMode === 'classify') {
                drawClassifications(cw, ch);
            } else {
                drawDetections(cw, ch);
            }

            drawScanline(cw, ch);
            drawFrameBorder(cw, ch);

            rafId = requestAnimationFrame(render);
        }
        rafId = requestAnimationFrame(render);
    }

    function drawDetections(cw, ch) {
        for (const det of currentDetections) {
            const [nx1, ny1, nx2, ny2] = det.bbox;
            const x1 = nx1 * cw;
            const y1 = ny1 * ch;
            const x2 = nx2 * cw;
            const y2 = ny2 * ch;
            const bw = x2 - x1;
            const bh = y2 - y1;

            // Draw polygon mask for segmentation mode
            if (det.polygon && det.polygon.length > 2) {
                ctx.beginPath();
                ctx.moveTo(det.polygon[0][0] * cw, det.polygon[0][1] * ch);
                for (let i = 1; i < det.polygon.length; i++) {
                    ctx.lineTo(det.polygon[i][0] * cw, det.polygon[i][1] * ch);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(0, 217, 255, 0.1)';
                ctx.fill();
                ctx.strokeStyle = CYAN_DIM;
                ctx.lineWidth = 1;
                ctx.stroke();
            }

            // Corner brackets (JARVIS style)
            const cornerLen = Math.min(bw, bh) * 0.2;
            const clampedLen = Math.max(8, Math.min(cornerLen, 30));
            ctx.strokeStyle = CYAN;
            ctx.lineWidth = 2;
            ctx.lineCap = 'square';

            // Top-left
            ctx.beginPath();
            ctx.moveTo(x1, y1 + clampedLen);
            ctx.lineTo(x1, y1);
            ctx.lineTo(x1 + clampedLen, y1);
            ctx.stroke();

            // Top-right
            ctx.beginPath();
            ctx.moveTo(x2 - clampedLen, y1);
            ctx.lineTo(x2, y1);
            ctx.lineTo(x2, y1 + clampedLen);
            ctx.stroke();

            // Bottom-left
            ctx.beginPath();
            ctx.moveTo(x1, y2 - clampedLen);
            ctx.lineTo(x1, y2);
            ctx.lineTo(x1 + clampedLen, y2);
            ctx.stroke();

            // Bottom-right
            ctx.beginPath();
            ctx.moveTo(x2 - clampedLen, y2);
            ctx.lineTo(x2, y2);
            ctx.lineTo(x2, y2 - clampedLen);
            ctx.stroke();

            // Label background
            const label = `${det.class} ${Math.round(det.confidence * 100)}%`;
            ctx.font = "500 11px 'JetBrains Mono', monospace";
            const tw = ctx.measureText(label).width;
            const labelH = 18;
            const labelY = y1 - labelH - 4;

            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.fillRect(x1, labelY, tw + 12, labelH);
            ctx.strokeStyle = CYAN;
            ctx.lineWidth = 1;
            ctx.strokeRect(x1, labelY, tw + 12, labelH);

            ctx.fillStyle = CYAN;
            ctx.textBaseline = 'middle';
            ctx.fillText(label, x1 + 6, labelY + labelH / 2);

            // Subtle fill inside box
            ctx.fillStyle = CYAN_FILL;
            ctx.fillRect(x1, y1, bw, bh);
        }
    }

    function drawClassifications(cw, ch) {
        if (currentDetections.length === 0) return;

        const startY = ch * 0.15;
        const startX = cw * 0.05;

        ctx.font = "500 10px 'JetBrains Mono', monospace";
        ctx.fillStyle = CYAN_DIM;
        ctx.textBaseline = 'top';
        ctx.fillText('CLASSIFICATION', startX, startY - 20);

        currentDetections.forEach((cls, i) => {
            const y = startY + i * 32;
            const barW = 180;
            const fillW = barW * cls.confidence;

            // Bar background
            ctx.fillStyle = 'rgba(0, 217, 255, 0.06)';
            ctx.fillRect(startX, y, barW, 20);

            // Bar fill
            ctx.fillStyle = 'rgba(0, 217, 255, 0.25)';
            ctx.fillRect(startX, y, fillW, 20);

            // Bar border
            ctx.strokeStyle = CYAN_DIM;
            ctx.lineWidth = 1;
            ctx.strokeRect(startX, y, barW, 20);

            // Label
            ctx.fillStyle = CYAN;
            ctx.font = "500 11px 'JetBrains Mono', monospace";
            ctx.textBaseline = 'middle';
            ctx.fillText(
                `${cls.class} ${Math.round(cls.confidence * 100)}%`,
                startX + barW + 10,
                y + 10
            );
        });
    }

    function drawScanline(cw, ch) {
        scanlineY = (scanlineY + 1.5) % ch;
        const gradient = ctx.createLinearGradient(0, scanlineY - 2, 0, scanlineY + 2);
        gradient.addColorStop(0, 'rgba(0, 217, 255, 0)');
        gradient.addColorStop(0.5, 'rgba(0, 217, 255, 0.12)');
        gradient.addColorStop(1, 'rgba(0, 217, 255, 0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, scanlineY - 2, cw, 4);
    }

    function drawFrameBorder(cw, ch) {
        const inset = 8;
        const cornerLen = 40;
        ctx.strokeStyle = 'rgba(0, 217, 255, 0.15)';
        ctx.lineWidth = 1;
        ctx.lineCap = 'square';

        // Top-left
        ctx.beginPath();
        ctx.moveTo(inset, inset + cornerLen);
        ctx.lineTo(inset, inset);
        ctx.lineTo(inset + cornerLen, inset);
        ctx.stroke();

        // Top-right
        ctx.beginPath();
        ctx.moveTo(cw - inset - cornerLen, inset);
        ctx.lineTo(cw - inset, inset);
        ctx.lineTo(cw - inset, inset + cornerLen);
        ctx.stroke();

        // Bottom-left
        ctx.beginPath();
        ctx.moveTo(inset, ch - inset - cornerLen);
        ctx.lineTo(inset, ch - inset);
        ctx.lineTo(inset + cornerLen, ch - inset);
        ctx.stroke();

        // Bottom-right
        ctx.beginPath();
        ctx.moveTo(cw - inset - cornerLen, ch - inset);
        ctx.lineTo(cw - inset, ch - inset);
        ctx.lineTo(cw - inset, ch - inset - cornerLen);
        ctx.stroke();
    }

    // ─── Detection List ──────────────────────────

    function updateDetectionsList() {
        if (currentMode === 'classify') {
            detectionsEl.innerHTML = currentDetections.map(c =>
                `<div class="vision-det-item">
                    <span class="vision-det-name">${c.class}</span>
                    <div class="vision-det-bar-bg"><div class="vision-det-bar-fill" style="width:${Math.round(c.confidence * 100)}%"></div></div>
                    <span class="vision-det-conf">${Math.round(c.confidence * 100)}%</span>
                </div>`
            ).join('');
            return;
        }

        // Group by class
        const groups = {};
        for (const d of currentDetections) {
            if (!groups[d.class]) groups[d.class] = { count: 0, maxConf: 0 };
            groups[d.class].count++;
            groups[d.class].maxConf = Math.max(groups[d.class].maxConf, d.confidence);
        }

        const sorted = Object.entries(groups).sort((a, b) => b[1].count - a[1].count);
        detectionsEl.innerHTML = sorted.map(([name, g]) =>
            `<div class="vision-det-item">
                <span class="vision-det-name">${name}${g.count > 1 ? ' x' + g.count : ''}</span>
                <div class="vision-det-bar-bg"><div class="vision-det-bar-fill" style="width:${Math.round(g.maxConf * 100)}%"></div></div>
                <span class="vision-det-conf">${Math.round(g.maxConf * 100)}%</span>
            </div>`
        ).join('');
    }

    // ─── Mode Switching ──────────────────────────

    document.querySelectorAll('.vision-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.vision-mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            mode = btn.dataset.mode;
            currentDetections = [];
            detectionsEl.innerHTML = '';
        });
    });

    // ─── Confidence Slider ───────────────────────

    confSlider.addEventListener('input', () => {
        confThreshold = parseInt(confSlider.value) / 100;
        confValueEl.textContent = confSlider.value + '%';
    });

    // ─── Auto-stop on view change ────────────────

    window.addEventListener('nex:viewchange', (e) => {
        if (e.detail.view !== 'vision' && active) {
            stopCamera();
        }
    });
})();
