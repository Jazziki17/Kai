/**
 * ═══════════════════════════════════════════════════════════
 * THOUGHT CLOUD — Floating Neural Thought Nodes
 * ═══════════════════════════════════════════════════════════
 *
 * Creates floating "thought bubbles" on the canvas that drift
 * organically, connected by neural pathways. Each thought
 * represents a task or process, visualizing Kai's internal
 * thinking flow.
 *
 * The thoughts follow the mouse cursor with a delayed,
 * elastic "following the thought" effect — as if the AI's
 * attention is being drawn to where you look.
 */

class ThoughtCloud {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.thoughts = [];
        this.mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
        this.time = 0;

        this.config = {
            glowColors: {
                system:     { r: 0,   g: 240, b: 255 },
                voice:      { r: 0,   g: 240, b: 255 },
                speech:     { r: 255, g: 0,   b: 170 },
                vision:     { r: 180, g: 74,  b: 255 },
                io:         { r: 0,   g: 255, b: 136 },
            },
            statusSymbols: {
                done:       '✓',
                active:     '◉',
                processing: '⟳',
                pending:    '○',
            },
            orbitRadius: 280,
            nodeSize: 6,
            trailLength: 8,
        };

        this._resize();
        this._bindEvents();
        this._fetchThoughts();
        this._animate();
    }

    _resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    _bindEvents() {
        window.addEventListener('resize', () => this._resize());
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });
    }

    async _fetchThoughts() {
        try {
            const res = await fetch('/api/thoughts');
            const data = await res.json();
            this._initThoughts(data.thoughts);
        } catch {
            // Fallback thoughts if API is unavailable
            this._initThoughts([
                { id: 1, text: 'System boot', status: 'done', type: 'system' },
                { id: 2, text: 'Neural sync', status: 'active', type: 'speech' },
                { id: 3, text: 'Vision calibrate', status: 'processing', type: 'vision' },
                { id: 4, text: 'Audio pipeline', status: 'active', type: 'voice' },
                { id: 5, text: 'Memory index', status: 'done', type: 'io' },
                { id: 6, text: 'Intent model', status: 'pending', type: 'speech' },
            ]);
        }
    }

    _initThoughts(thoughtData) {
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2;

        this.thoughts = thoughtData.map((t, i) => {
            const angle = (i / thoughtData.length) * Math.PI * 2;
            const radius = this.config.orbitRadius + (Math.random() - 0.5) * 100;
            const color = this.config.glowColors[t.type] || this.config.glowColors.system;

            return {
                ...t,
                x: cx + Math.cos(angle) * radius,
                y: cy + Math.sin(angle) * radius,
                targetX: cx + Math.cos(angle) * radius,
                targetY: cy + Math.sin(angle) * radius,
                vx: 0,
                vy: 0,
                baseAngle: angle,
                orbitRadius: radius,
                orbitSpeed: 0.0003 + Math.random() * 0.0004,
                bobSpeed: 0.5 + Math.random() * 0.5,
                bobAmount: 5 + Math.random() * 10,
                color: color,
                alpha: t.status === 'done' ? 0.4 : 0.8,
                size: this.config.nodeSize + (t.status === 'active' ? 3 : 0),
                trail: [],
            };
        });
    }

    _animate() {
        this.time += 0.016; // ~60fps
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        if (this.thoughts.length > 0) {
            this._updateThoughts();
            this._drawConnectionLines();
            this._drawThoughtTrails();
            this._drawThoughtNodes();
            this._drawCoreBeams();
        }

        requestAnimationFrame(() => this._animate());
    }

    _updateThoughts() {
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2;

        // Mouse influence center — blend between screen center and mouse
        const influenceX = cx + (this.mouse.x - cx) * 0.15;
        const influenceY = cy + (this.mouse.y - cy) * 0.15;

        for (const t of this.thoughts) {
            // Orbit around the influence point
            t.baseAngle += t.orbitSpeed;

            // Target position: orbit + bob
            const bobY = Math.sin(this.time * t.bobSpeed) * t.bobAmount;
            const bobX = Math.cos(this.time * t.bobSpeed * 0.7) * t.bobAmount * 0.5;

            t.targetX = influenceX + Math.cos(t.baseAngle) * t.orbitRadius + bobX;
            t.targetY = influenceY + Math.sin(t.baseAngle) * t.orbitRadius + bobY;

            // Elastic following — smooth interpolation toward target
            // This creates the "following the thought" effect
            const springForce = 0.02;
            const dampening = 0.92;

            t.vx += (t.targetX - t.x) * springForce;
            t.vy += (t.targetY - t.y) * springForce;
            t.vx *= dampening;
            t.vy *= dampening;
            t.x += t.vx;
            t.y += t.vy;

            // Trail
            t.trail.push({ x: t.x, y: t.y });
            if (t.trail.length > this.config.trailLength) {
                t.trail.shift();
            }
        }
    }

    _drawConnectionLines() {
        // Draw faint lines between adjacent thoughts (neural pathways)
        for (let i = 0; i < this.thoughts.length; i++) {
            const a = this.thoughts[i];
            const b = this.thoughts[(i + 1) % this.thoughts.length];

            const gradient = this.ctx.createLinearGradient(a.x, a.y, b.x, b.y);
            gradient.addColorStop(0, `rgba(${a.color.r}, ${a.color.g}, ${a.color.b}, 0.08)`);
            gradient.addColorStop(0.5, `rgba(${a.color.r}, ${a.color.g}, ${a.color.b}, 0.03)`);
            gradient.addColorStop(1, `rgba(${b.color.r}, ${b.color.g}, ${b.color.b}, 0.08)`);

            this.ctx.beginPath();
            this.ctx.moveTo(a.x, a.y);

            // Curved connection (bezier) for organic feel
            const mx = (a.x + b.x) / 2 + Math.sin(this.time * 0.5 + i) * 20;
            const my = (a.y + b.y) / 2 + Math.cos(this.time * 0.3 + i) * 20;
            this.ctx.quadraticCurveTo(mx, my, b.x, b.y);

            this.ctx.strokeStyle = gradient;
            this.ctx.lineWidth = 1;
            this.ctx.stroke();
        }
    }

    _drawThoughtTrails() {
        for (const t of this.thoughts) {
            if (t.trail.length < 2) continue;

            for (let i = 1; i < t.trail.length; i++) {
                const alpha = (i / t.trail.length) * 0.15 * t.alpha;
                const size = (i / t.trail.length) * t.size * 0.6;

                this.ctx.beginPath();
                this.ctx.arc(t.trail[i].x, t.trail[i].y, size, 0, Math.PI * 2);
                this.ctx.fillStyle = `rgba(${t.color.r}, ${t.color.g}, ${t.color.b}, ${alpha})`;
                this.ctx.fill();
            }
        }
    }

    _drawThoughtNodes() {
        for (const t of this.thoughts) {
            const { r, g, b } = t.color;

            // Outer glow
            const glowSize = t.size * (t.status === 'active' ? 5 : 3);
            const glowGradient = this.ctx.createRadialGradient(
                t.x, t.y, 0,
                t.x, t.y, glowSize
            );
            glowGradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${t.alpha * 0.3})`);
            glowGradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, ${t.alpha * 0.08})`);
            glowGradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

            this.ctx.beginPath();
            this.ctx.arc(t.x, t.y, glowSize, 0, Math.PI * 2);
            this.ctx.fillStyle = glowGradient;
            this.ctx.fill();

            // Core dot
            this.ctx.beginPath();
            this.ctx.arc(t.x, t.y, t.size, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${t.alpha})`;
            this.ctx.fill();

            // Bright center
            this.ctx.beginPath();
            this.ctx.arc(t.x, t.y, t.size * 0.4, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(255, 255, 255, ${t.alpha * 0.6})`;
            this.ctx.fill();

            // Processing ring animation
            if (t.status === 'processing' || t.status === 'active') {
                const ringSize = t.size * 2.5 + Math.sin(this.time * 3) * 2;
                this.ctx.beginPath();
                this.ctx.arc(t.x, t.y, ringSize, 0, Math.PI * 2);
                this.ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${t.alpha * 0.3})`;
                this.ctx.lineWidth = 1;
                this.ctx.setLineDash([3, 5]);
                this.ctx.lineDashOffset = -this.time * 30;
                this.ctx.stroke();
                this.ctx.setLineDash([]);
            }

            // Label
            if (t.size > 4) {
                this.ctx.font = '10px "Share Tech Mono", monospace';
                this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${t.alpha * 0.7})`;
                this.ctx.textAlign = 'center';
                this.ctx.fillText(
                    t.text.toUpperCase(),
                    t.x,
                    t.y + t.size + 16
                );
            }
        }
    }

    _drawCoreBeams() {
        // Draw faint beams from center to active thoughts
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2;

        for (const t of this.thoughts) {
            if (t.status !== 'active' && t.status !== 'processing') continue;

            const { r, g, b } = t.color;
            const gradient = this.ctx.createLinearGradient(cx, cy, t.x, t.y);
            gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.04)`);
            gradient.addColorStop(0.3, `rgba(${r}, ${g}, ${b}, 0.02)`);
            gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.06)`);

            this.ctx.beginPath();
            this.ctx.moveTo(cx, cy);
            this.ctx.lineTo(t.x, t.y);
            this.ctx.strokeStyle = gradient;
            this.ctx.lineWidth = 1.5;
            this.ctx.stroke();
        }
    }
}

// Initialize
const thoughtCloud = new ThoughtCloud('thought-canvas');
