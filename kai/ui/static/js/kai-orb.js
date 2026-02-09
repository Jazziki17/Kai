/**
 * KAI ORB — Minimalist Neural Interface
 *
 * A single centered orb with concentric rings, sparse particles,
 * and tick marks. Reacts to voice amplitude. Clean and minimal.
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
    let voiceAmp = 0;         // 0–1, voice amplitude
    let targetAmp = 0;
    let isListening = true;
    let orbScale = 1;

    // Responsive base size
    function getBaseRadius() {
        return Math.min(W, H) * 0.16;
    }

    // ─── Particles ──────────────────────────────────────
    const particles = [];
    const PARTICLE_COUNT = 50;

    function initParticles() {
        particles.length = 0;
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            particles.push(createParticle());
        }
    }

    function createParticle() {
        const angle = Math.random() * Math.PI * 2;
        const dist = getBaseRadius() * (1.2 + Math.random() * 3.5);
        return {
            x: cx + Math.cos(angle) * dist,
            y: cy + Math.sin(angle) * dist,
            size: Math.random() * 1.5 + 0.3,
            alpha: Math.random() * 0.3 + 0.08,
            speed: Math.random() * 0.15 + 0.05,
            angle: angle,
            dist: dist,
            drift: (Math.random() - 0.5) * 0.002,
            pulseSpeed: Math.random() * 0.02 + 0.01,
            pulseOffset: Math.random() * Math.PI * 2,
        };
    }

    function updateParticles() {
        for (const p of particles) {
            // Slow orbital drift
            p.angle += p.drift;

            // Voice pushes particles outward gently
            const voicePush = voiceAmp * 15;
            const currentDist = p.dist + voicePush;

            p.x = cx + Math.cos(p.angle) * currentDist;
            p.y = cy + Math.sin(p.angle) * currentDist;

            // Pulse alpha
            p.alpha = 0.08 + Math.sin(time * p.pulseSpeed * 60 + p.pulseOffset) * 0.1 + 0.05;
            p.alpha += voiceAmp * 0.15;
        }
    }

    function drawParticles() {
        for (const p of particles) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(160, 190, 220, ${p.alpha})`;
            ctx.fill();
        }
    }

    // ─── Rings ──────────────────────────────────────────

    function drawRings() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;

        // Ring definitions: [radiusMultiplier, lineWidth, alpha, dashPattern, rotationSpeed]
        const rings = [
            // Inner core ring — solid, bright
            { r: 1.0,  w: 2.0, a: 0.5,  dash: [],          rot: 0 },
            // Second ring — thin
            { r: 1.25, w: 0.8, a: 0.15, dash: [],          rot: 0 },
            // Dashed ring
            { r: 1.55, w: 0.8, a: 0.12, dash: [4, 12],     rot: 0.05 },
            // Dotted ring
            { r: 1.85, w: 0.6, a: 0.08, dash: [1.5, 10],   rot: -0.03 },
            // Outer dashed ring
            { r: 2.2,  w: 0.5, a: 0.06, dash: [6, 20],     rot: 0.02 },
            // Very faint outer ring
            { r: 2.6,  w: 0.4, a: 0.04, dash: [2, 25],     rot: -0.015 },
        ];

        for (const ring of rings) {
            const radius = base * ring.r * breathe;
            const alpha = ring.a + voiceAmp * ring.a * 0.8;

            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(time * ring.rot);

            ctx.beginPath();
            ctx.arc(0, 0, radius, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(120, 180, 230, ${alpha})`;
            ctx.lineWidth = ring.w;
            if (ring.dash.length) {
                ctx.setLineDash(ring.dash);
            }
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.restore();
        }
    }

    // ─── Tick Marks ─────────────────────────────────────

    function drawTicks() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;

        // Tick groups at different radii
        const tickGroups = [
            // [radius multiplier, count, length, width, alpha]
            { r: 1.55, count: 4,  len: 8,  w: 1.2, a: 0.2  },   // Cardinal ticks on dashed ring
            { r: 1.85, count: 8,  len: 5,  w: 0.8, a: 0.12 },   // Small ticks
            { r: 2.2,  count: 4,  len: 10, w: 0.6, a: 0.08 },   // Outer cardinal
            { r: 1.0,  count: 2,  len: 6,  w: 1.5, a: 0.25 },   // Top/bottom on core ring
        ];

        for (const group of tickGroups) {
            const radius = base * group.r * breathe;
            const alpha = group.a + voiceAmp * group.a;

            for (let i = 0; i < group.count; i++) {
                const angle = (i / group.count) * Math.PI * 2 - Math.PI / 2;
                const innerR = radius - group.len / 2;
                const outerR = radius + group.len / 2;

                const x1 = cx + Math.cos(angle) * innerR;
                const y1 = cy + Math.sin(angle) * innerR;
                const x2 = cx + Math.cos(angle) * outerR;
                const y2 = cy + Math.sin(angle) * outerR;

                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = `rgba(140, 180, 220, ${alpha})`;
                ctx.lineWidth = group.w;
                ctx.stroke();
            }
        }
    }

    // ─── Voice Bars (small EQ-style indicators) ─────────

    function drawVoiceBars() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;

        // Top bars
        const topY = cy - base * 1.55 * breathe - 20;
        drawBarGroup(cx, topY, 3, true);

        // Bottom bars
        const bottomY = cy + base * 1.55 * breathe + 20;
        drawBarGroup(cx, bottomY, 3, false);
    }

    function drawBarGroup(x, y, count, up) {
        const gap = 4;
        const barWidth = 2;
        const startX = x - ((count - 1) * gap) / 2;
        const dir = up ? -1 : 1;

        for (let i = 0; i < count; i++) {
            const bx = startX + i * gap;
            // Each bar has different animation
            const phase = i * 0.8;
            const amp = voiceAmp * 0.6 + 0.15;
            const height = (Math.sin(time * 3 + phase) * 0.5 + 0.5) * amp * 14 + 2;
            const alpha = 0.15 + voiceAmp * 0.3;

            ctx.beginPath();
            ctx.moveTo(bx, y);
            ctx.lineTo(bx, y + height * dir);
            ctx.strokeStyle = `rgba(140, 190, 230, ${alpha})`;
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

        // Subtle inner glow
        const glow = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius * 1.1);
        glow.addColorStop(0, `rgba(80, 150, 220, ${0.03 + voiceAmp * 0.04})`);
        glow.addColorStop(0.5, `rgba(60, 120, 200, ${0.015 + voiceAmp * 0.02})`);
        glow.addColorStop(1, 'rgba(40, 80, 160, 0)');

        ctx.beginPath();
        ctx.arc(cx, cy, radius * 1.1, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();

        // Core circle fill — very subtle
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.65, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(15, 20, 35, ${0.6 + voiceAmp * 0.2})`;
        ctx.fill();

        // Core circle stroke
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.65, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(100, 170, 230, ${0.25 + voiceAmp * 0.3})`;
        ctx.lineWidth = 1.5 + voiceAmp * 0.5;
        ctx.stroke();

        // "KAI" text
        const fontSize = base * 0.28;
        ctx.font = `300 ${fontSize}px 'Rajdhani', sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = `rgba(180, 210, 240, ${0.6 + voiceAmp * 0.3})`;
        ctx.letterSpacing = '8px';
        // Manual letter spacing since canvas doesn't support it
        const letters = 'KAI';
        const spacing = fontSize * 0.55;
        const startX = cx - ((letters.length - 1) * spacing) / 2;
        for (let i = 0; i < letters.length; i++) {
            ctx.fillText(letters[i], startX + i * spacing, cy + 2);
        }
    }

    // ─── Arc Segments (decorative partial arcs) ─────────

    function drawArcSegments() {
        const base = getBaseRadius();
        const breathe = 1 + voiceAmp * 0.06;

        // Partial arcs that rotate slowly
        const arcs = [
            { r: 1.38, start: -0.3, end: 0.3,   a: 0.12, w: 1.5, speed: 0.08 },
            { r: 1.38, start: 2.8,  end: 3.4,    a: 0.12, w: 1.5, speed: 0.08 },
            { r: 2.0,  start: 1.2,  end: 1.8,    a: 0.06, w: 0.8, speed: -0.04 },
            { r: 2.0,  start: 4.4,  end: 5.0,    a: 0.06, w: 0.8, speed: -0.04 },
            { r: 0.82, start: 0.8,  end: 1.3,    a: 0.18, w: 2.0, speed: -0.12 },
            { r: 0.82, start: 3.9,  end: 4.4,    a: 0.18, w: 2.0, speed: -0.12 },
        ];

        for (const arc of arcs) {
            const radius = base * arc.r * breathe;
            const alpha = arc.a + voiceAmp * arc.a * 0.5;
            const rotation = time * arc.speed;

            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(rotation);

            ctx.beginPath();
            ctx.arc(0, 0, radius, arc.start, arc.end);
            ctx.strokeStyle = `rgba(120, 180, 230, ${alpha})`;
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
        cy = H / 2 - H * 0.04; // Slightly above center
        initParticles();
    }

    // ─── WebSocket Connection ────────────────────────────
    // Connects to the Kai API server for real-time events.
    // Falls back to simulation if server is unavailable.

    let voiceInterval = null;
    let isSpeaking = false;
    let ws = null;
    let wsConnected = false;
    let wsReconnectTimer = null;

    function connectWebSocket() {
        const wsUrl = `ws://${location.hostname || 'localhost'}:${location.port || 8420}/ws`;

        try {
            ws = new WebSocket(wsUrl);
        } catch {
            fallbackToSimulation();
            return;
        }

        ws.onopen = () => {
            wsConnected = true;
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
            statusEl.textContent = 'RECONNECTING';
            wsReconnectTimer = setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            ws.close();
        };
    }

    function handleServerEvent(msg) {
        const { type, data } = msg;

        switch (type) {
            case 'command.response':
                // Real response from CommandHandler
                stopSpeaking();
                showTranscript(data.text || '');
                // Pulse the orb to show activity
                targetAmp = 0.6;
                setTimeout(() => { targetAmp = 0; }, 600);
                break;

            case 'system.ready':
                showTranscript('Kai is ready.');
                targetAmp = 0.4;
                setTimeout(() => { targetAmp = 0; }, 500);
                break;

            case 'system.module_error':
                showTranscript('Module error: ' + (data.module || 'unknown'));
                break;

            case 'connected':
                // Welcome message from server
                break;

            default:
                break;
        }
    }

    function startSpeaking() {
        isSpeaking = true;
        statusEl.classList.add('active');
        statusEl.textContent = 'PROCESSING';

        voiceInterval = setInterval(() => {
            targetAmp = 0.3 + Math.random() * 0.7;
        }, 80);
    }

    function stopSpeaking() {
        isSpeaking = false;
        clearInterval(voiceInterval);
        targetAmp = 0;
        statusEl.classList.remove('active');
        statusEl.textContent = 'LISTENING';
    }

    let transcriptTimer = null;

    function showTranscript(text) {
        // Clear any pending hide
        if (transcriptTimer) clearTimeout(transcriptTimer);

        transcriptEl.textContent = text;
        transcriptEl.style.whiteSpace = 'pre-wrap';
        transcriptEl.classList.add('visible');

        // Longer display for longer text
        const displayTime = Math.max(4000, Math.min(text.length * 50, 12000));
        transcriptTimer = setTimeout(() => {
            transcriptEl.classList.remove('visible');
        }, displayTime);
    }

    // Fallback: simulate voice if no WebSocket server available
    function fallbackToSimulation() {
        setInterval(() => {
            if (Math.random() < 0.25) {
                startSpeaking();
                setTimeout(() => {
                    stopSpeaking();
                    const msgs = [
                        'Initializing neural pathways...',
                        'Voice pattern recognized.',
                        'Processing ambient data.',
                        'System calibration complete.',
                        'Ready for next command.',
                    ];
                    showTranscript(msgs[Math.floor(Math.random() * msgs.length)]);
                }, 1500 + Math.random() * 3000);
            }
        }, 4000);
    }

    // ─── Command Input ──────────────────────────────────

    let commandVisible = false;

    document.addEventListener('keydown', (e) => {
        if (e.key === '/' || e.key === 'Enter') {
            if (!commandVisible) {
                e.preventDefault();
                commandBar.classList.add('visible');
                commandInput.focus();
                commandVisible = true;
            }
        }
        if (e.key === 'Escape') {
            commandBar.classList.remove('visible');
            commandInput.blur();
            commandInput.value = '';
            commandVisible = false;
        }
    });

    commandInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && commandInput.value.trim()) {
            const text = commandInput.value.trim();
            commandInput.value = '';
            commandBar.classList.remove('visible');
            commandVisible = false;

            // Show what the user said
            showTranscript('> ' + text);

            // Send command via WebSocket
            if (ws && wsConnected) {
                ws.send(JSON.stringify({ type: 'command', command: text }));
            }

            // Show thinking state — LLM is processing
            startSpeaking();
            statusEl.textContent = 'THINKING';
        }
    });

    // Click on orb triggers a pulse
    canvas.addEventListener('click', (e) => {
        if (!commandVisible) {
            targetAmp = 0.9;
            setTimeout(() => { targetAmp = 0; }, 300);
        }
    });

    // ─── Animation Loop ─────────────────────────────────

    function animate() {
        time += 0.016;

        // Smooth voice amplitude
        voiceAmp += (targetAmp - voiceAmp) * 0.12;

        // Clear
        ctx.clearRect(0, 0, W, H);

        // Draw layers back to front
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
