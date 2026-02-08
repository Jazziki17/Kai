/**
 * ═══════════════════════════════════════════════════════════
 * KAI DASHBOARD — Main Application Controller
 * ═══════════════════════════════════════════════════════════
 *
 * Handles:
 * - Clock and system metrics
 * - Waveform visualizations on module cards
 * - Command input processing
 * - Thought stream rendering
 * - Dynamic metric simulation
 */

// ─── Clock ──────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('en-GB', { hour12: false });
    const date = now.toISOString().slice(0, 10).replace(/-/g, '.');

    document.getElementById('clock').textContent = time;
    document.getElementById('date').textContent = date;
}
setInterval(updateClock, 1000);
updateClock();

// ─── Uptime ─────────────────────────────────────────────────
const startTime = Date.now();
function updateUptime() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    document.getElementById('uptime').textContent = `${h}:${m}:${s}`;
}
setInterval(updateUptime, 1000);

// ─── Waveform Visualizer ────────────────────────────────────
class WaveformViz {
    constructor(canvasId, color) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.color = color;
        this.data = new Array(30).fill(0);
        this.offset = Math.random() * 100;
    }

    update() {
        if (!this.canvas) return;

        // Generate organic waveform data
        this.data.shift();
        const t = Date.now() * 0.003 + this.offset;
        const value = (Math.sin(t) * 0.3 + Math.sin(t * 2.3) * 0.2 +
                       Math.sin(t * 5.7) * 0.15 + Math.random() * 0.2) * 0.5 + 0.5;
        this.data.push(value);

        this.draw();
    }

    draw() {
        const { ctx, canvas } = this;
        const w = canvas.width;
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        // Draw waveform
        ctx.beginPath();
        ctx.moveTo(0, h);

        for (let i = 0; i < this.data.length; i++) {
            const x = (i / (this.data.length - 1)) * w;
            const y = h - this.data[i] * h * 0.8;
            if (i === 0) {
                ctx.lineTo(x, y);
            } else {
                const prevX = ((i - 1) / (this.data.length - 1)) * w;
                const prevY = h - this.data[i - 1] * h * 0.8;
                const cpX = (prevX + x) / 2;
                ctx.bezierCurveTo(cpX, prevY, cpX, y, x, y);
            }
        }

        ctx.lineTo(w, h);
        ctx.closePath();

        // Gradient fill
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, this.color + '0.4)');
        gradient.addColorStop(1, this.color + '0.02)');
        ctx.fillStyle = gradient;
        ctx.fill();

        // Line on top
        ctx.beginPath();
        for (let i = 0; i < this.data.length; i++) {
            const x = (i / (this.data.length - 1)) * w;
            const y = h - this.data[i] * h * 0.8;
            if (i === 0) ctx.moveTo(x, y);
            else {
                const prevX = ((i - 1) / (this.data.length - 1)) * w;
                const prevY = h - this.data[i - 1] * h * 0.8;
                const cpX = (prevX + x) / 2;
                ctx.bezierCurveTo(cpX, prevY, cpX, y, x, y);
            }
        }
        ctx.strokeStyle = this.color + '0.8)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
    }
}

const waveforms = [
    new WaveformViz('waveform-voice', 'rgba(0, 240, 255, '),
    new WaveformViz('waveform-speech', 'rgba(255, 0, 170, '),
    new WaveformViz('waveform-vision', 'rgba(180, 74, 255, '),
    new WaveformViz('waveform-io', 'rgba(0, 255, 136, '),
];

setInterval(() => {
    waveforms.forEach(w => w.update());
}, 80);

// ─── Metric Simulation ─────────────────────────────────────
let eventCount = 0;
function updateMetrics() {
    const cpu = 15 + Math.sin(Date.now() * 0.001) * 10 + Math.random() * 8;
    const mem = 35 + Math.sin(Date.now() * 0.0005) * 8 + Math.random() * 5;
    const net = 5 + Math.sin(Date.now() * 0.002) * 5 + Math.random() * 8;

    document.getElementById('cpu-bar').style.width = cpu + '%';
    document.getElementById('cpu-val').textContent = Math.round(cpu) + '%';
    document.getElementById('mem-bar').style.width = mem + '%';
    document.getElementById('mem-val').textContent = Math.round(mem) + '%';
    document.getElementById('net-bar').style.width = net + '%';
    document.getElementById('net-val').textContent = Math.round(net) + '%';
    document.getElementById('latency').textContent = Math.round(1 + Math.random() * 4) + 'ms';

    eventCount += Math.floor(Math.random() * 3);
    document.getElementById('event-count').textContent = eventCount;
}
setInterval(updateMetrics, 2000);

// ─── Thought Stream ─────────────────────────────────────────
async function loadThoughts() {
    try {
        const res = await fetch('/api/thoughts');
        const data = await res.json();
        renderThoughts(data.thoughts);
    } catch {
        renderThoughts([
            { id: 1, text: 'System initialized', status: 'done', type: 'system' },
            { id: 2, text: 'Awaiting input...', status: 'active', type: 'voice' },
        ]);
    }
}

function renderThoughts(thoughts) {
    const container = document.getElementById('thought-stream');
    document.getElementById('thought-count').textContent = thoughts.length;

    container.innerHTML = thoughts.map((t, i) => `
        <div class="thought-node thought-node--${t.status}"
             style="animation-delay: ${i * 0.1}s">
            <div class="thought-node__header">
                <span class="thought-node__type thought-node__type--${t.type}">
                    ${t.type}
                </span>
                <span class="thought-node__status">${t.status}</span>
            </div>
            <div class="thought-node__text">${t.text}</div>
        </div>
    `).join('');
}

loadThoughts();

// Periodically shuffle thought statuses for visual interest
setInterval(() => {
    const nodes = document.querySelectorAll('.thought-node');
    if (nodes.length === 0) return;

    const idx = Math.floor(Math.random() * nodes.length);
    const node = nodes[idx];
    const statuses = ['done', 'active', 'processing', 'pending'];
    const newStatus = statuses[Math.floor(Math.random() * statuses.length)];

    // Remove old status classes
    statuses.forEach(s => node.classList.remove(`thought-node--${s}`));
    node.classList.add(`thought-node--${newStatus}`);

    // Update status text
    const statusEl = node.querySelector('.thought-node__status');
    if (statusEl) statusEl.textContent = newStatus;
}, 4000);

// ─── Command Input ──────────────────────────────────────────
const commandField = document.getElementById('command-field');
const responseArea = document.getElementById('response-area');
const sendBtn = document.getElementById('send-btn');

const responses = {
    'time':     () => `Current time: ${new Date().toLocaleTimeString()}`,
    'status':   () => 'All systems operational. 4 modules active.',
    'help':     () => 'Available: time, status, hello, modules, clear',
    'hello':    () => 'Hello. I am Kai, your neural assistant.',
    'hi':       () => 'Greetings. How can I assist you?',
    'modules':  () => 'Active: VoiceListener, SpeechEngine, VisionCore, FileSystem',
    'clear':    () => { responseArea.innerHTML = ''; return null; },
    'shutdown': () => 'Shutdown requires physical confirmation. Stay online.',
};

function processCommand(text) {
    if (!text.trim()) return;

    // Add user line
    addResponseLine(text, 'user', '▸ YOU');

    // Find response
    const key = Object.keys(responses).find(k =>
        text.toLowerCase().includes(k)
    );

    setTimeout(() => {
        const reply = key ? responses[key]() : `Processing: "${text}" — intent classification in progress...`;
        if (reply) {
            addResponseLine(reply, 'system', '[KAI]');
        }
    }, 300 + Math.random() * 500);

    // Add thought
    addNewThought(text);

    commandField.value = '';
    eventCount += 1;
}

function addResponseLine(text, type, prefix) {
    const line = document.createElement('div');
    line.className = `response-line response-line--${type}`;
    line.innerHTML = `<span class="response-prefix">${prefix}</span>${text}`;
    responseArea.appendChild(line);
    responseArea.scrollTop = responseArea.scrollHeight;
}

function addNewThought(text) {
    const container = document.getElementById('thought-stream');
    const types = ['voice', 'speech', 'vision', 'io', 'system'];
    const type = types[Math.floor(Math.random() * types.length)];

    const node = document.createElement('div');
    node.className = 'thought-node thought-node--active';
    node.innerHTML = `
        <div class="thought-node__header">
            <span class="thought-node__type thought-node__type--${type}">${type}</span>
            <span class="thought-node__status">active</span>
        </div>
        <div class="thought-node__text">${text}</div>
    `;

    container.insertBefore(node, container.firstChild);

    const count = parseInt(document.getElementById('thought-count').textContent) + 1;
    document.getElementById('thought-count').textContent = count;

    // Auto-complete after a delay
    setTimeout(() => {
        node.classList.remove('thought-node--active');
        node.classList.add('thought-node--done');
        const statusEl = node.querySelector('.thought-node__status');
        if (statusEl) statusEl.textContent = 'done';
    }, 3000 + Math.random() * 5000);
}

commandField.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        processCommand(commandField.value);
    }
});

sendBtn.addEventListener('click', () => {
    processCommand(commandField.value);
});

// ─── Module Card Hover Effects ──────────────────────────────
document.querySelectorAll('.module-card').forEach(card => {
    card.addEventListener('click', () => {
        const mod = card.dataset.module;
        addResponseLine(
            `Module diagnostic: ${mod.toUpperCase()} — nominal, latency <2ms`,
            'system',
            '[KAI]'
        );
    });
});

// ─── Core Orb Mouse Interaction ─────────────────────────────
const coreOrb = document.getElementById('core-orb');
document.addEventListener('mousemove', (e) => {
    const rect = coreOrb.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = (e.clientX - cx) * 0.02;
    const dy = (e.clientY - cy) * 0.02;

    coreOrb.style.transform = `translate(${dx}px, ${dy}px)`;
});

// ─── Startup Animation ─────────────────────────────────────
const startupMessages = [
    'Neural pathways initialized...',
    'Voice recognition module online.',
    'Speech engine calibrated.',
    'Vision core activated.',
    'File system indexed. 0 errors.',
    'All systems nominal. Awaiting command.',
];

startupMessages.forEach((msg, i) => {
    setTimeout(() => {
        addResponseLine(msg, 'system', '[KAI]');
    }, 800 + i * 600);
});
