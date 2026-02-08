/**
 * ═══════════════════════════════════════════════════════════
 * PARTICLE SYSTEM — Neural Cloud Network
 * ═══════════════════════════════════════════════════════════
 *
 * Creates a floating particle cloud with interconnecting lines,
 * simulating a neural network / constellation effect.
 *
 * Particles drift organically and connect when close enough,
 * creating a living, breathing background.
 *
 * Mouse interaction: particles gently gravitate toward the cursor,
 * as if "following the thought."
 */

class ParticleSystem {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.particles = [];
        this.mouse = { x: -1000, y: -1000 };
        this.config = {
            particleCount: 120,
            maxSpeed: 0.4,
            connectionDistance: 150,
            mouseRadius: 200,
            mouseForce: 0.02,
            colors: [
                'rgba(0, 240, 255, ',    // cyan
                'rgba(255, 0, 170, ',    // magenta
                'rgba(180, 74, 255, ',   // purple
            ],
            lineColor: 'rgba(0, 240, 255, ',
        };

        this._resize();
        this._initParticles();
        this._bindEvents();
        this._animate();
    }

    _resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    _initParticles() {
        this.particles = [];
        for (let i = 0; i < this.config.particleCount; i++) {
            this.particles.push(this._createParticle());
        }
    }

    _createParticle() {
        const colorBase = this.config.colors[
            Math.floor(Math.random() * this.config.colors.length)
        ];
        return {
            x: Math.random() * this.canvas.width,
            y: Math.random() * this.canvas.height,
            vx: (Math.random() - 0.5) * this.config.maxSpeed,
            vy: (Math.random() - 0.5) * this.config.maxSpeed,
            radius: Math.random() * 2 + 0.5,
            colorBase: colorBase,
            alpha: Math.random() * 0.5 + 0.2,
            pulseSpeed: Math.random() * 0.02 + 0.005,
            pulseOffset: Math.random() * Math.PI * 2,
        };
    }

    _bindEvents() {
        window.addEventListener('resize', () => {
            this._resize();
        });

        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });

        window.addEventListener('mouseleave', () => {
            this.mouse.x = -1000;
            this.mouse.y = -1000;
        });
    }

    _animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this._updateParticles();
        this._drawConnections();
        this._drawParticles();
        requestAnimationFrame(() => this._animate());
    }

    _updateParticles() {
        const time = Date.now() * 0.001;

        for (const p of this.particles) {
            // Mouse attraction — particles follow the cursor gently
            const dx = this.mouse.x - p.x;
            const dy = this.mouse.y - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < this.config.mouseRadius && dist > 0) {
                const force = this.config.mouseForce * (1 - dist / this.config.mouseRadius);
                p.vx += (dx / dist) * force;
                p.vy += (dy / dist) * force;
            }

            // Organic drift — subtle sine wave movement
            p.vx += Math.sin(time + p.pulseOffset) * 0.002;
            p.vy += Math.cos(time * 0.7 + p.pulseOffset) * 0.002;

            // Friction — prevents infinite acceleration
            p.vx *= 0.99;
            p.vy *= 0.99;

            // Speed limit
            const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
            if (speed > this.config.maxSpeed) {
                p.vx = (p.vx / speed) * this.config.maxSpeed;
                p.vy = (p.vy / speed) * this.config.maxSpeed;
            }

            // Move
            p.x += p.vx;
            p.y += p.vy;

            // Wrap around edges
            if (p.x < -20) p.x = this.canvas.width + 20;
            if (p.x > this.canvas.width + 20) p.x = -20;
            if (p.y < -20) p.y = this.canvas.height + 20;
            if (p.y > this.canvas.height + 20) p.y = -20;

            // Pulse alpha
            p.alpha = 0.2 + Math.sin(time * p.pulseSpeed * 60 + p.pulseOffset) * 0.15 + 0.15;
        }
    }

    _drawParticles() {
        for (const p of this.particles) {
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            this.ctx.fillStyle = p.colorBase + p.alpha + ')';
            this.ctx.fill();

            // Glow effect
            if (p.radius > 1.5) {
                this.ctx.beginPath();
                this.ctx.arc(p.x, p.y, p.radius * 3, 0, Math.PI * 2);
                this.ctx.fillStyle = p.colorBase + (p.alpha * 0.15) + ')';
                this.ctx.fill();
            }
        }
    }

    _drawConnections() {
        const maxDist = this.config.connectionDistance;

        for (let i = 0; i < this.particles.length; i++) {
            for (let j = i + 1; j < this.particles.length; j++) {
                const a = this.particles[i];
                const b = this.particles[j];
                const dx = a.x - b.x;
                const dy = a.y - b.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < maxDist) {
                    const alpha = (1 - dist / maxDist) * 0.15;
                    this.ctx.beginPath();
                    this.ctx.moveTo(a.x, a.y);
                    this.ctx.lineTo(b.x, b.y);
                    this.ctx.strokeStyle = this.config.lineColor + alpha + ')';
                    this.ctx.lineWidth = 0.5;
                    this.ctx.stroke();
                }
            }
        }

        // Mouse connections — draw lines from cursor to nearby particles
        for (const p of this.particles) {
            const dx = this.mouse.x - p.x;
            const dy = this.mouse.y - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < this.config.mouseRadius) {
                const alpha = (1 - dist / this.config.mouseRadius) * 0.25;
                this.ctx.beginPath();
                this.ctx.moveTo(this.mouse.x, this.mouse.y);
                this.ctx.lineTo(p.x, p.y);
                this.ctx.strokeStyle = 'rgba(255, 0, 170, ' + alpha + ')';
                this.ctx.lineWidth = 0.8;
                this.ctx.stroke();
            }
        }
    }
}

// Initialize
const particleSystem = new ParticleSystem('particle-canvas');
