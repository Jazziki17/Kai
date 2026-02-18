/**
 * NEX BOOT SEQUENCE — Matrix-inspired cinematic startup.
 * Phase 1: Digital rain (0-5s)
 * Phase 2: Terminal text (5-12s)
 * Phase 3: Orb formation particles (12-18s)
 * Phase 4: Reveal UI (18-22s)
 * Skippable with any key/click.
 */

(() => {
    const overlay = document.getElementById('boot-sequence');
    if (!overlay) return;

    // Skip if already booted this session
    if (sessionStorage.getItem('nex-booted')) {
        overlay.remove();
        return;
    }

    const rainCanvas = document.getElementById('matrix-rain-canvas');
    const terminalEl = document.getElementById('boot-terminal');
    const particleCanvas = document.getElementById('boot-particle-canvas');

    let skipped = false;
    let animFrameId = null;

    // ─── Matrix Rain ─────────────────────────────────────

    class MatrixRain {
        constructor(canvas) {
            this.canvas = canvas;
            this.ctx = canvas.getContext('2d');
            this.resize();
            this.chars = 'NEXネックスABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*アイウエオカキクケコサシスセソタチツテト';
            this.drops = [];
            for (let i = 0; i < this.columns; i++) {
                this.drops[i] = Math.random() * -100;
            }
            this.running = true;
        }

        resize() {
            this.width = window.innerWidth;
            this.height = window.innerHeight;
            this.canvas.width = this.width;
            this.canvas.height = this.height;
            this.fontSize = 14;
            this.columns = Math.floor(this.width / this.fontSize);
        }

        draw() {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
            this.ctx.fillRect(0, 0, this.width, this.height);
            this.ctx.font = `${this.fontSize}px 'JetBrains Mono', monospace`;

            for (let i = 0; i < this.drops.length; i++) {
                const char = this.chars[Math.floor(Math.random() * this.chars.length)];
                const x = i * this.fontSize;
                const y = this.drops[i] * this.fontSize;

                // Lead character is bright white-green
                if (Math.random() > 0.5) {
                    this.ctx.fillStyle = '#AAFFAA';
                } else {
                    this.ctx.fillStyle = `rgba(0, 255, 65, ${0.4 + Math.random() * 0.6})`;
                }
                this.ctx.fillText(char, x, y);

                if (y > this.height && Math.random() > 0.975) {
                    this.drops[i] = 0;
                }
                this.drops[i]++;
            }
        }

        animate() {
            if (!this.running) return;
            this.draw();
            animFrameId = requestAnimationFrame(() => this.animate());
        }

        stop() {
            this.running = false;
        }
    }

    // ─── Terminal Boot Text ──────────────────────────────

    const bootMessages = [
        'INITIALIZING NEX CORE...',
        'LOADING NEURAL PATHWAYS...',
        'CONNECTING TO LOCAL INFERENCE ENGINE...',
        'CALIBRATING VOICE SYNTHESIS...',
        'MOUNTING MEMORY STORE...',
        'BOOTING CONSCIOUSNESS MATRIX...',
        'ALL SYSTEMS NOMINAL.',
    ];

    async function typeText(element, text, speed = 30) {
        for (let i = 0; i < text.length; i++) {
            if (skipped) return;
            element.textContent += text[i];
            await new Promise(r => setTimeout(r, speed));
        }
    }

    async function runTerminal() {
        if (!terminalEl || skipped) return;
        terminalEl.style.opacity = '1';

        for (const msg of bootMessages) {
            if (skipped) return;
            const line = document.createElement('div');
            line.className = 'boot-line';
            line.innerHTML = '<span class="boot-prompt">&gt;</span> <span class="boot-text"></span><span class="boot-cursor"></span>';
            terminalEl.appendChild(line);

            const textSpan = line.querySelector('.boot-text');
            await typeText(textSpan, msg);
            // Remove cursor from completed line
            const cursor = line.querySelector('.boot-cursor');
            if (cursor) cursor.remove();

            // Play synth beep
            if (window.NexSounds) window.NexSounds.play('bootBeep');

            await new Promise(r => setTimeout(r, 300));
        }
    }

    // ─── Particle Convergence ────────────────────────────

    class ParticleConverge {
        constructor(canvas) {
            this.canvas = canvas;
            this.ctx = canvas.getContext('2d');
            this.width = window.innerWidth;
            this.height = window.innerHeight;
            this.canvas.width = this.width;
            this.canvas.height = this.height;
            this.cx = this.width / 2;
            this.cy = this.height / 2;
            this.particles = [];
            this.running = true;
            this.frame = 0;
            this.shockwave = 0;

            for (let i = 0; i < 400; i++) {
                const angle = Math.random() * Math.PI * 2;
                const dist = 300 + Math.random() * 500;
                this.particles.push({
                    x: this.cx + Math.cos(angle) * dist,
                    y: this.cy + Math.sin(angle) * dist,
                    size: Math.random() * 2.5 + 0.5,
                    speed: 1.5 + Math.random() * 3,
                    opacity: Math.random() * 0.7 + 0.3,
                    arrived: false,
                });
            }
        }

        animate() {
            if (!this.running) return;
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.08)';
            this.ctx.fillRect(0, 0, this.width, this.height);

            let arrivedCount = 0;

            for (const p of this.particles) {
                const dx = this.cx - p.x;
                const dy = this.cy - p.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist > 8) {
                    p.x += (dx / dist) * p.speed;
                    p.y += (dy / dist) * p.speed;
                } else {
                    p.arrived = true;
                    arrivedCount++;
                }

                this.ctx.beginPath();
                this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                this.ctx.fillStyle = p.arrived
                    ? `rgba(0, 255, 65, ${p.opacity})`
                    : `rgba(0, 255, 65, ${p.opacity * 0.7})`;
                this.ctx.fill();
            }

            // Core glow when particles arrive
            if (arrivedCount > 100) {
                const glowIntensity = Math.min(1, (arrivedCount - 100) / 200);
                const gradient = this.ctx.createRadialGradient(
                    this.cx, this.cy, 0, this.cx, this.cy, 80
                );
                gradient.addColorStop(0, `rgba(0, 255, 65, ${0.3 * glowIntensity})`);
                gradient.addColorStop(0.5, `rgba(0, 255, 65, ${0.1 * glowIntensity})`);
                gradient.addColorStop(1, 'rgba(0, 255, 65, 0)');
                this.ctx.fillStyle = gradient;
                this.ctx.fillRect(this.cx - 80, this.cy - 80, 160, 160);
            }

            // Shockwave ring when most particles arrive
            if (arrivedCount > 350 && this.shockwave === 0) {
                this.shockwave = 1;
            }

            if (this.shockwave > 0 && this.shockwave < 300) {
                this.ctx.beginPath();
                this.ctx.arc(this.cx, this.cy, this.shockwave * 3, 0, Math.PI * 2);
                this.ctx.strokeStyle = `rgba(0, 255, 65, ${0.5 * (1 - this.shockwave / 300)})`;
                this.ctx.lineWidth = 2;
                this.ctx.stroke();
                this.shockwave += 4;
            }

            this.frame++;
            animFrameId = requestAnimationFrame(() => this.animate());
        }

        stop() {
            this.running = false;
        }
    }

    // ─── Sequence Controller ─────────────────────────────

    let rain = null;
    let particles = null;

    async function runBootSequence() {
        // Phase 1: Matrix Rain (0-5s)
        overlay.style.display = 'flex';
        if (rainCanvas) {
            rain = new MatrixRain(rainCanvas);
            rainCanvas.style.opacity = '1';
            rain.animate();
        }

        await wait(5000);
        if (skipped) return;

        // Fade rain, start terminal
        if (rainCanvas) {
            rainCanvas.style.transition = 'opacity 1s ease-out';
            rainCanvas.style.opacity = '0.15';
        }

        // Phase 2: Terminal (5-12s)
        await runTerminal();
        if (skipped) return;

        await wait(500);
        if (skipped) return;

        // Fade terminal
        if (terminalEl) {
            terminalEl.style.transition = 'opacity 0.8s ease-out';
            terminalEl.style.opacity = '0';
        }

        await wait(800);
        if (skipped) return;

        // Phase 3: Particle convergence (12-18s)
        if (rain) rain.stop();
        if (rainCanvas) rainCanvas.style.opacity = '0';

        if (particleCanvas) {
            particleCanvas.style.opacity = '1';
            particles = new ParticleConverge(particleCanvas);
            particles.animate();
        }

        await wait(4000);
        if (skipped) return;

        // Phase 4: Reveal
        finishBoot();
    }

    function finishBoot() {
        if (skipped) return;
        skipped = true;
        sessionStorage.setItem('nex-booted', '1');

        if (rain) rain.stop();
        if (particles) particles.stop();
        if (animFrameId) cancelAnimationFrame(animFrameId);

        overlay.style.transition = 'opacity 1.2s ease-out';
        overlay.style.opacity = '0';

        setTimeout(() => {
            overlay.remove();
            // Play orb appear sound
            if (window.NexSounds) window.NexSounds.play('orbAppear');
        }, 1200);
    }

    function skipBoot() {
        if (skipped) return;
        skipped = true;
        sessionStorage.setItem('nex-booted', '1');

        if (rain) rain.stop();
        if (particles) particles.stop();
        if (animFrameId) cancelAnimationFrame(animFrameId);

        overlay.style.transition = 'opacity 0.4s ease-out';
        overlay.style.opacity = '0';
        setTimeout(() => overlay.remove(), 400);
    }

    function wait(ms) {
        return new Promise(r => {
            const id = setTimeout(r, ms);
            // Store so skip can resolve
            wait._timers = wait._timers || [];
            wait._timers.push(id);
        });
    }

    // Skip on any key or click
    document.addEventListener('keydown', skipBoot, { once: true });
    overlay.addEventListener('click', skipBoot, { once: true });

    // Start after a brief delay
    setTimeout(runBootSequence, 100);
})();
