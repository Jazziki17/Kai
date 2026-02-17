/**
 * NEX ORB — Neural Interface with view switching, tool feedback, and event dispatch.
 */

(() => {
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const statusEl = document.getElementById('status');
    const transcriptEl = document.getElementById('transcript');
    const commandBar = document.getElementById('command-bar');
    const commandInput = document.getElementById('command-input');

    let W, H, cx, cy;
    let time = 0;
    let voiceAmp = 0;
    let targetAmp = 0;
    let isListening = true;

    // Current view: 'orb' | 'dashboard' | 'services' | 'logs' | 'vision' | 'settings'
    let currentView = 'orb';

    function getBaseRadius() {
        return Math.min(W, H) * 0.16;
    }

    // ─── Particles ──────────────────────────────────────
    const particles = [];
    const PARTICLE_COUNT = 50;

    function initParticles() {
        particles.length = 0;
        for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(createParticle());
    }

    function createParticle() {
        const angle = Math.random() * Math.PI * 2;
        const dist = getBaseRadius() * (1.2 + Math.random() * 3.5);
        return {
            x: cx + Math.cos(angle) * dist,
            y: cy + Math.sin(angle) * dist,
            size: Math.random() * 1.5 + 0.3,
            alpha: Math.random() * 0.3 + 0.08,
            angle, dist,
            drift: (Math.random() - 0.5) * 0.002,
            pulseSpeed: Math.random() * 0.02 + 0.01,
            pulseOffset: Math.random() * Math.PI * 2,
        };
    }

    function updateParticles() {
        for (const p of particles) {
            p.angle += p.drift;
            const currentDist = p.dist + voiceAmp * 15;
            p.x = cx + Math.cos(p.angle) * currentDist;
            p.y = cy + Math.sin(p.angle) * currentDist;
            p.alpha = 0.08 + Math.sin(time * p.pulseSpeed * 60 + p.pulseOffset) * 0.1 + 0.05 + voiceAmp * 0.15;
        }
    }

    function drawParticles() {
        for (const p of particles) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(255, 255, 255, ${p.alpha})`;
            ctx.fill();
        }
    }

    // ─── Rings ──────────────────────────────────────────

    function drawRings() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;
        const rings = [
            { r: 1.0,  w: 2.0, a: 0.5,  dash: [],        rot: 0 },
            { r: 1.25, w: 0.8, a: 0.15, dash: [],        rot: 0 },
            { r: 1.55, w: 0.8, a: 0.12, dash: [4, 12],   rot: 0.05 },
            { r: 1.85, w: 0.6, a: 0.08, dash: [1.5, 10], rot: -0.03 },
            { r: 2.2,  w: 0.5, a: 0.06, dash: [6, 20],   rot: 0.02 },
            { r: 2.6,  w: 0.4, a: 0.04, dash: [2, 25],   rot: -0.015 },
        ];
        for (const ring of rings) {
            const radius = base * ring.r * breathe;
            const alpha = ring.a + voiceAmp * ring.a * 0.8;
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(time * ring.rot);
            ctx.beginPath();
            ctx.arc(0, 0, radius, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(255, 255, 255, ${alpha})`;
            ctx.lineWidth = ring.w;
            if (ring.dash.length) ctx.setLineDash(ring.dash);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();
        }
    }

    // ─── Ticks ──────────────────────────────────────────

    function drawTicks() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;
        const groups = [
            { r: 1.55, count: 4,  len: 8,  w: 1.2, a: 0.2 },
            { r: 1.85, count: 8,  len: 5,  w: 0.8, a: 0.12 },
            { r: 2.2,  count: 4,  len: 10, w: 0.6, a: 0.08 },
            { r: 1.0,  count: 2,  len: 6,  w: 1.5, a: 0.25 },
        ];
        for (const g of groups) {
            const radius = base * g.r * breathe;
            const alpha = g.a + voiceAmp * g.a;
            for (let i = 0; i < g.count; i++) {
                const angle = (i / g.count) * Math.PI * 2 - Math.PI / 2;
                const x1 = cx + Math.cos(angle) * (radius - g.len / 2);
                const y1 = cy + Math.sin(angle) * (radius - g.len / 2);
                const x2 = cx + Math.cos(angle) * (radius + g.len / 2);
                const y2 = cy + Math.sin(angle) * (radius + g.len / 2);
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = `rgba(255, 255, 255, ${alpha})`;
                ctx.lineWidth = g.w;
                ctx.stroke();
            }
        }
    }

    // ─── Voice Bars ─────────────────────────────────────

    function drawVoiceBars() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;
        drawBarGroup(cx, cy - base * 1.55 * breathe - 20, 3, true);
        drawBarGroup(cx, cy + base * 1.55 * breathe + 20, 3, false);
    }

    function drawBarGroup(x, y, count, up) {
        const gap = 4, barWidth = 2, dir = up ? -1 : 1;
        const startX = x - ((count - 1) * gap) / 2;
        for (let i = 0; i < count; i++) {
            const amp = voiceAmp * 0.6 + 0.15;
            const height = (Math.sin(time * 3 + i * 0.8) * 0.5 + 0.5) * amp * 14 + 2;
            ctx.beginPath();
            ctx.moveTo(startX + i * gap, y);
            ctx.lineTo(startX + i * gap, y + height * dir);
            ctx.strokeStyle = `rgba(255, 255, 255, ${0.15 + voiceAmp * 0.3})`;
            ctx.lineWidth = barWidth;
            ctx.lineCap = 'round';
            ctx.stroke();
        }
    }

    // ─── Core Orb ───────────────────────────────────────

    function drawOrb() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;
        const radius = base * breathe;

        const glow = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius * 1.1);
        glow.addColorStop(0, `rgba(200, 210, 220, ${0.03 + voiceAmp * 0.04})`);
        glow.addColorStop(0.5, `rgba(180, 190, 200, ${0.015 + voiceAmp * 0.02})`);
        glow.addColorStop(1, 'rgba(150, 160, 170, 0)');
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 1.1, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.65, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(8, 8, 12, ${0.6 + voiceAmp * 0.2})`;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.65, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.25 + voiceAmp * 0.3})`;
        ctx.lineWidth = 1.5 + voiceAmp * 0.5;
        ctx.stroke();

        const fontSize = base * 0.28;
        ctx.font = `300 ${fontSize}px 'Inter', sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = `rgba(255, 255, 255, ${0.6 + voiceAmp * 0.3})`;
        const letters = 'NEX';
        const spacing = fontSize * 0.55;
        const startX = cx - ((letters.length - 1) * spacing) / 2;
        for (let i = 0; i < letters.length; i++) {
            ctx.fillText(letters[i], startX + i * spacing, cy + 2);
        }
    }

    // ─── Arc Segments ───────────────────────────────────

    function drawArcSegments() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;
        const arcs = [
            { r: 1.38, start: -0.3, end: 0.3, a: 0.12, w: 1.5, speed: 0.08 },
            { r: 1.38, start: 2.8, end: 3.4, a: 0.12, w: 1.5, speed: 0.08 },
            { r: 2.0, start: 1.2, end: 1.8, a: 0.06, w: 0.8, speed: -0.04 },
            { r: 2.0, start: 4.4, end: 5.0, a: 0.06, w: 0.8, speed: -0.04 },
            { r: 0.82, start: 0.8, end: 1.3, a: 0.18, w: 2.0, speed: -0.12 },
            { r: 0.82, start: 3.9, end: 4.4, a: 0.18, w: 2.0, speed: -0.12 },
        ];
        for (const arc of arcs) {
            const radius = base * arc.r * breathe;
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(time * arc.speed);
            ctx.beginPath();
            ctx.arc(0, 0, radius, arc.start, arc.end);
            ctx.strokeStyle = `rgba(255, 255, 255, ${arc.a + voiceAmp * arc.a * 0.5})`;
            ctx.lineWidth = arc.w;
            ctx.lineCap = 'round';
            ctx.stroke();
            ctx.restore();
        }
    }

    // ─── Resize ─────────────────────────────────────────

    function resize() {
        const dpr = window.devicePixelRatio || 1;
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';
        ctx.scale(dpr, dpr);
        cx = W / 2;
        cy = H / 2 - H * 0.04;
        initParticles();
    }

    // ─── View Switching ─────────────────────────────────

    window.switchView = function(view) {
        currentView = view;
        const dashView = document.getElementById('dashboard-view');
        const servView = document.getElementById('services-view');
        const logsView = document.getElementById('logs-view');
        const visionView = document.getElementById('vision-view');
        const settView = document.getElementById('settings-view');

        // Toggle overlays
        dashView.classList.toggle('active', view === 'dashboard');
        servView.classList.toggle('active', view === 'services');
        logsView.classList.toggle('active', view === 'logs');
        visionView.classList.toggle('active', view === 'vision');
        settView.classList.toggle('active', view === 'settings');
        canvas.classList.toggle('dimmed', view !== 'orb');

        // Update nav buttons
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });

        // Dispatch event for sub-modules
        window.dispatchEvent(new CustomEvent('nex:viewchange', { detail: { view } }));
    };

    // Nav button clicks (only buttons with data-view, skip fullscreen/history)
    document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Tab key cycles views
    const views = ['orb', 'dashboard', 'services', 'logs', 'vision', 'settings'];
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Tab' && !commandInput.matches(':focus')) {
            e.preventDefault();
            const next = views[(views.indexOf(currentView) + 1) % views.length];
            switchView(next);
        }
    });

    // ─── WebSocket ──────────────────────────────────────

    let voiceInterval = null;
    let isSpeaking = false;
    let ws = null;
    let wsConnected = false;

    async function connectWebSocket() {
        // Fetch session token for WebSocket auth
        let token = '';
        try {
            const resp = await fetch(`${location.protocol}//${location.hostname || 'localhost'}:${location.port || 8420}/api/auth/token`);
            const data = await resp.json();
            token = data.token || '';
        } catch {
            setTimeout(connectWebSocket, 3000);
            return;
        }

        const wsUrl = `ws://${location.hostname || 'localhost'}:${location.port || 8420}/ws`;
        try { ws = new WebSocket(wsUrl); } catch { return; }

        ws.onopen = () => {
            // Send auth token as first message
            ws.send(JSON.stringify({ type: 'auth', token: token }));
            wsConnected = true;
            window._nexWs = ws;
            statusEl.textContent = 'CONNECTED';
            statusEl.classList.add('active');
            setTimeout(() => {
                statusEl.classList.remove('active');
                statusEl.textContent = 'LISTENING';
            }, 1500);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleServerEvent(msg);
            } catch {}
        };

        ws.onclose = () => {
            wsConnected = false;
            window._nexWs = null;
            statusEl.textContent = 'RECONNECTING';
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => ws.close();
    }

    function handleServerEvent(msg) {
        const { type, data } = msg;

        // Dispatch CustomEvent for dashboard/settings/services/logs JS to listen
        window.dispatchEvent(new CustomEvent('nex:' + type, { detail: data }));

        switch (type) {
            case 'mic.transcribed':
                showTranscript('> ' + (data.text || ''));
                statusEl.textContent = 'PROCESSING';
                statusEl.classList.add('active');
                targetAmp = 0.5;
                startSpeaking();
                break;

            case 'command.response':
                stopSpeaking();
                if (!data.command || !data.command.startsWith('_')) {
                    showTranscript(data.text || '');
                    // Brief "RESPONDING" state before going back to LISTENING
                    statusEl.textContent = 'RESPONDING';
                    statusEl.classList.add('active');
                    setTimeout(() => {
                        statusEl.classList.remove('active');
                        statusEl.textContent = 'LISTENING';
                    }, 2000);
                }
                targetAmp = 0.6;
                setTimeout(() => { targetAmp = 0; }, 600);
                break;

            case 'tool.executing':
                statusEl.textContent = (data.name || 'TOOL').toUpperCase().replace(/_/g, ' ');
                statusEl.classList.add('tool-active');
                targetAmp = 0.3;
                break;

            case 'tool.completed':
                statusEl.textContent = 'THINKING';
                statusEl.classList.remove('tool-active');
                break;

            case 'system.ready':
                // Silent startup — no transcript, no orb pulse
                statusEl.textContent = 'ONLINE';
                statusEl.classList.add('active');
                setTimeout(() => {
                    statusEl.classList.remove('active');
                    statusEl.textContent = 'LISTENING';
                }, 2000);
                break;

            case 'mic.level':
                updateAudioMeter(data.level || 0, data.recording || false);
                break;

            case 'mic.speech_detected':
                if (data.active) {
                    statusEl.textContent = 'HEARING';
                    statusEl.classList.add('active');
                }
                break;

            case 'connected':
                break;
        }
    }

    // ─── Audio Level Meter ────────────────────────────

    const audioMeter = document.getElementById('audio-meter');
    const meterBars = audioMeter ? audioMeter.querySelectorAll('.bar') : [];

    function updateAudioMeter(level, recording) {
        if (!audioMeter) return;
        const barCount = meterBars.length;
        // Create a symmetric pattern: edges lower, center higher
        const mid = Math.floor(barCount / 2);
        for (let i = 0; i < barCount; i++) {
            const distFromCenter = Math.abs(i - mid);
            const threshold = (barCount - distFromCenter) * (100 / barCount) * 0.6;
            const isActive = level > threshold;
            meterBars[i].classList.toggle('active', isActive);
            if (isActive) {
                const h = Math.max(4, Math.min(18, 4 + (level / 100) * 14 - distFromCenter * 2));
                meterBars[i].style.height = h + 'px';
            } else {
                meterBars[i].style.height = '4px';
            }
        }
        audioMeter.classList.toggle('hearing', recording);
    }

    function startSpeaking() {
        isSpeaking = true;
        statusEl.classList.add('active');
        statusEl.textContent = 'THINKING';
        voiceInterval = setInterval(() => { targetAmp = 0.3 + Math.random() * 0.7; }, 80);
    }

    function stopSpeaking() {
        isSpeaking = false;
        clearInterval(voiceInterval);
        targetAmp = 0;
        statusEl.classList.remove('active');
        statusEl.classList.remove('tool-active');
        statusEl.textContent = 'LISTENING';
    }

    let transcriptTimer = null;
    function showTranscript(text) {
        if (transcriptTimer) clearTimeout(transcriptTimer);
        transcriptEl.textContent = text;
        transcriptEl.style.whiteSpace = 'pre-wrap';
        transcriptEl.classList.add('visible');
        const displayTime = Math.max(4000, Math.min(text.length * 50, 12000));
        transcriptTimer = setTimeout(() => transcriptEl.classList.remove('visible'), displayTime);
    }

    // ─── Command Input ──────────────────────────────────

    let commandVisible = false;

    document.addEventListener('keydown', (e) => {
        if ((e.key === '/' || e.key === 'Enter') && !commandVisible && currentView === 'orb') {
            e.preventDefault();
            commandBar.classList.add('visible');
            commandInput.focus();
            commandVisible = true;
        }
        if (e.key === 'Escape' && commandVisible) {
            e.preventDefault();
            e.stopPropagation();
            commandBar.classList.remove('visible');
            commandInput.blur();
            commandInput.value = '';
            commandVisible = false;
        }
    });

    commandInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const text = commandInput.value.trim();
            if (text) {
                commandInput.value = '';
                commandBar.classList.remove('visible');
                commandVisible = false;
                showTranscript('> ' + text);
                window.dispatchEvent(new CustomEvent('nex:user.command', { detail: { text } }));
                if (ws && wsConnected) {
                    ws.send(JSON.stringify({ type: 'command', command: text }));
                }
                startSpeaking();
            } else {
                // Empty Enter closes the command bar
                commandBar.classList.remove('visible');
                commandInput.blur();
                commandVisible = false;
            }
        }
    });

    canvas.addEventListener('click', () => {
        if (!commandVisible) {
            targetAmp = 0.9;
            setTimeout(() => { targetAmp = 0; }, 300);
        }
    });

    // ─── Fullscreen Toggle ───────────────────────────────

    const fsBtn = document.getElementById('fullscreen-btn');
    const fsExpandIcon = document.getElementById('fs-expand-icon');
    const fsShrinkIcon = document.getElementById('fs-shrink-icon');
    let isFullscreen = false;

    function updateFullscreenUI(fs) {
        isFullscreen = fs;
        document.body.classList.toggle('fullscreen', fs);
        if (fsExpandIcon) fsExpandIcon.style.display = fs ? 'none' : '';
        if (fsShrinkIcon) fsShrinkIcon.style.display = fs ? '' : 'none';
    }

    if (fsBtn) {
        fsBtn.addEventListener('click', () => {
            // Prefer Electron IPC, fallback to Web Fullscreen API
            if (window.nexAPI && window.nexAPI.toggleFullscreen) {
                window.nexAPI.toggleFullscreen();
            } else if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                document.documentElement.requestFullscreen().catch(() => {});
            }
        });
    }

    // Listen for fullscreen state changes from Electron IPC
    if (window.nexAPI && window.nexAPI.onFullscreenChange) {
        window.nexAPI.onFullscreenChange(updateFullscreenUI);
    }

    // Listen for Web Fullscreen API changes (fallback)
    document.addEventListener('fullscreenchange', () => {
        updateFullscreenUI(!!document.fullscreenElement);
    });

    // ─── Animation Loop ─────────────────────────────────

    function animate() {
        time += 0.016;
        voiceAmp += (targetAmp - voiceAmp) * 0.12;
        ctx.clearRect(0, 0, W, H);
        drawParticles();
        drawRings();
        drawArcSegments();
        drawTicks();
        drawVoiceBars();
        drawOrb();
        updateParticles();
        requestAnimationFrame(animate);
    }

    // ─── Init ───────────────────────────────────────────

    window.addEventListener('resize', resize);
    resize();
    connectWebSocket();
    animate();
})();
