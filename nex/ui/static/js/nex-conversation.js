/**
 * NEX Conversation Feed — Claude Code-style live conversation overlay.
 * Displays actions, thinking states, and responses with opacity cascade.
 */

(() => {
    const feed = document.getElementById('conversation-feed');
    if (!feed) return;

    const MAX_VISIBLE = 50;
    const COLLAPSE_LINES = 3;

    let entries = [];
    let activeThinking = null;
    let commandStartTime = null;
    let lastUserCommand = '';

    // ─── Entry Management ──────────────────────────────

    function generateId() {
        return 'cf-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    }

    function formatTime(ms) {
        if (ms == null) return null;
        if (ms < 1000) return (ms / 1000).toFixed(1) + 's';
        if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
        const m = Math.floor(ms / 60000);
        const s = Math.round((ms % 60000) / 1000);
        return m + 'm ' + s + 's';
    }

    function escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function truncate(s, max) {
        if (!s) return '';
        return s.length > max ? s.slice(0, max) + '\u2026' : s;
    }

    function addEntry(type, title, lines, processingTimeMs) {
        // If we're replacing a thinking entry
        if (activeThinking) {
            removeEntry(activeThinking);
            activeThinking = null;
        }

        const id = generateId();
        const entry = {
            id,
            type,
            title,
            lines: lines || [],
            processingTimeMs: processingTimeMs != null ? processingTimeMs : null,
            timestamp: new Date(),
            expanded: false,
        };

        entries.push(entry);

        if (entries.length > MAX_VISIBLE) {
            entries = entries.slice(-MAX_VISIBLE);
        }

        render();
        return id;
    }

    function removeEntry(id) {
        entries = entries.filter(e => e.id !== id);
    }

    function showThinking(title) {
        if (activeThinking) {
            removeEntry(activeThinking);
        }
        activeThinking = addEntry('thinking', title || 'Thinking...', []);
        return activeThinking;
    }

    // ─── Rendering ─────────────────────────────────────

    function render() {
        feed.innerHTML = '';

        entries.forEach((entry, index) => {
            const el = document.createElement('div');
            el.className = 'cf-entry cf-' + entry.type;
            el.dataset.id = entry.id;

            const dot = getDot(entry.type);
            const dotColor = getDotColor(entry.type);

            // Title line
            const titleLine = document.createElement('div');
            titleLine.className = 'cf-title-line';

            const dotSpan = document.createElement('span');
            dotSpan.className = 'cf-dot';
            dotSpan.style.color = dotColor;
            dotSpan.textContent = dot + ' ';

            const titleSpan = document.createElement('span');
            titleSpan.className = 'cf-title';

            if (entry.type === 'thinking') {
                titleSpan.textContent = entry.title;
                const dotsSpan = document.createElement('span');
                dotsSpan.className = 'cf-thinking-dots';
                for (let i = 0; i < 5; i++) {
                    const d = document.createElement('span');
                    d.textContent = '\u25CF';
                    d.style.animationDelay = (i * 0.2) + 's';
                    dotsSpan.appendChild(d);
                }
                titleLine.appendChild(dotSpan);
                titleLine.appendChild(titleSpan);
                titleLine.appendChild(dotsSpan);
            } else {
                titleSpan.textContent = entry.title;
                titleLine.appendChild(dotSpan);
                titleLine.appendChild(titleSpan);

                if (entry.processingTimeMs != null) {
                    const badge = document.createElement('span');
                    badge.className = 'cf-time-badge';
                    badge.textContent = formatTime(entry.processingTimeMs);
                    titleLine.appendChild(badge);
                }
            }

            el.appendChild(titleLine);

            // Output lines (sub-steps)
            if (entry.lines.length > 0) {
                const linesContainer = document.createElement('div');
                linesContainer.className = 'cf-lines' + (entry.expanded ? ' expanded' : '');

                const visibleLines = entry.expanded ? entry.lines : entry.lines.slice(0, COLLAPSE_LINES);
                visibleLines.forEach(line => {
                    const lineEl = document.createElement('div');
                    lineEl.className = 'cf-line';
                    lineEl.innerHTML = '<span class="cf-substep-mark">\u23BF</span> ' + escHtml(line);
                    linesContainer.appendChild(lineEl);
                });

                if (!entry.expanded && entry.lines.length > COLLAPSE_LINES) {
                    const more = document.createElement('div');
                    more.className = 'cf-more';
                    more.textContent = '\u2026 +' + (entry.lines.length - COLLAPSE_LINES) + ' lines (hover to expand)';
                    linesContainer.appendChild(more);
                }

                el.appendChild(linesContainer);

                el.addEventListener('mouseenter', () => {
                    if (entry.lines.length > COLLAPSE_LINES) {
                        entry.expanded = true;
                        render();
                    }
                });
                el.addEventListener('mouseleave', () => {
                    if (entry.expanded) {
                        entry.expanded = false;
                        render();
                    }
                });
            }

            feed.appendChild(el);
        });

        // Auto-scroll to bottom (newest messages)
        feed.scrollTop = feed.scrollHeight;
    }

    function getDot(type) {
        switch (type) {
            case 'action': return '\u23FA';   // ⏺
            case 'user': return '\u23FA';     // ⏺
            case 'thinking': return '\u273B'; // ✻
            case 'success': return '\u2713';  // ✓
            case 'error': return '\u2717';    // ✗
            default: return '\u23FA';
        }
    }

    function getDotColor(type) {
        switch (type) {
            case 'action': return '#00FF41';
            case 'user': return 'rgba(255,255,255,0.6)';
            case 'thinking': return '#ffaa00';
            case 'success': return '#00ff88';
            case 'error': return '#ff4444';
            default: return '#00FF41';
        }
    }

    // ─── Event Wiring ──────────────────────────────────

    let currentServicesUsed = [];

    // System ready — silent entry
    window.addEventListener('nex:system.ready', () => {
        addEntry('success', 'All systems ready', []);
    });

    // Voice command transcribed
    window.addEventListener('nex:mic.transcribed', (e) => {
        const text = e.detail.text || '';
        commandStartTime = Date.now();
        lastUserCommand = text;
        currentServicesUsed = ['stt'];
        addEntry('user', 'You \u2014 ' + truncate(text, 50), []);
        showThinking('Thinking...');
    });

    // Typed command submitted
    window.addEventListener('nex:user.command', (e) => {
        const text = e.detail.text || '';
        commandStartTime = Date.now();
        lastUserCommand = text;
        currentServicesUsed = [];
        addEntry('user', 'You \u2014 ' + truncate(text, 50), []);
        showThinking('Thinking...');
    });

    // Tool executing
    window.addEventListener('nex:tool.executing', (e) => {
        const name = (e.detail.name || 'tool').replace(/_/g, ' ');
        currentServicesUsed.push(e.detail.name || 'tool');
        // Replace thinking with tool-specific thinking
        if (activeThinking) {
            removeEntry(activeThinking);
            activeThinking = null;
        }
        activeThinking = addEntry('thinking', 'Running ' + name + '...', []);
    });

    // ─── JSON Filter ────────────────────────────────────

    function filterJsonArtifacts(text) {
        if (!text) return text;
        const trimmed = text.trim();
        // If entire response is a JSON tool call, replace with generic message
        if ((trimmed.startsWith('{') || trimmed.startsWith('[')) &&
            (trimmed.endsWith('}') || trimmed.endsWith(']'))) {
            try {
                const parsed = JSON.parse(trimmed);
                if (parsed && typeof parsed === 'object' &&
                    ('name' in parsed || 'function' in parsed || 'parameters' in parsed || 'tool_call' in parsed)) {
                    return 'Processing your request...';
                }
                if (Array.isArray(parsed) && parsed.length > 0 && parsed[0] && 'name' in parsed[0]) {
                    return 'Processing your request...';
                }
            } catch (e) { /* not JSON, keep as-is */ }
        }
        // Strip inline JSON tool call blobs from within text
        return text.replace(/\{"(?:name|function|tool_call)"\s*:\s*"[^"]*"[^}]*\}/g, '').trim() || text;
    }

    // Command response — the main response handler
    window.addEventListener('nex:command.response', (e) => {
        let text = e.detail.text || '';
        const command = e.detail.command || '';

        // Skip internal/system commands
        if (command.startsWith('_')) return;

        // Filter any raw JSON tool call artifacts
        text = filterJsonArtifacts(text);

        const elapsed = commandStartTime ? Date.now() - commandStartTime : null;
        commandStartTime = null;

        // Split response into title + lines
        const allLines = text.split('\n').filter(l => l.trim());
        const title = allLines.length > 0 ? truncate(allLines[0], 60) : 'Done.';
        const subLines = allLines.length > 1 ? allLines.slice(1) : [];

        addEntry('action', 'Nex \u2014 ' + title, subLines, elapsed);

        // Dispatch for history
        window.dispatchEvent(new CustomEvent('nex:conversation.complete', {
            detail: {
                userPrompt: lastUserCommand || command,
                nexResponse: text,
                processingTimeMs: elapsed,
                servicesUsed: [...currentServicesUsed, 'tts'],
            }
        }));
        currentServicesUsed = [];
        lastUserCommand = '';
    });

    // ─── Visibility Control ────────────────────────────

    window.addEventListener('nex:viewchange', (e) => {
        const view = e.detail.view;
        feed.classList.toggle('visible', view === 'dashboard' || view === 'orb');
    });

    // Default: visible on orb view
    feed.classList.add('visible');

    // Expose for external use
    window.NexConversation = { addEntry, showThinking };
})();
