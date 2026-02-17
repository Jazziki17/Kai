/**
 * NEX Conversation Feed — Claude Code-style live conversation overlay.
 * Displays actions, thinking states, and responses with opacity cascade.
 */

(() => {
    const feed = document.getElementById('conversation-feed');
    if (!feed) return;

    const MAX_VISIBLE = 5;
    const OPACITY_LEVELS = [1.0, 0.85, 0.65, 0.40, 0.20];
    const COLLAPSE_LINES = 3;

    let entries = [];
    let activeThinking = null;  // Current thinking entry ID
    let commandStartTime = null; // For tracking processing time

    // ─── Entry Management ──────────────────────────────

    function generateId() {
        return 'cf-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    }

    function formatTime(ms) {
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

    function addEntry(type, title, lines, processingTimeMs) {
        // If we're replacing a thinking entry
        if (activeThinking) {
            removeEntry(activeThinking);
            activeThinking = null;
        }

        const id = generateId();
        const entry = {
            id,
            type,       // 'action' | 'thinking' | 'success' | 'error' | 'substep'
            title,
            lines: lines || [],
            processingTimeMs: processingTimeMs || null,
            timestamp: new Date(),
            expanded: false,
        };

        entries.unshift(entry);

        // Trim to max visible + 1 (for fade-out animation)
        if (entries.length > MAX_VISIBLE + 1) {
            entries = entries.slice(0, MAX_VISIBLE + 1);
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
            const opacity = OPACITY_LEVELS[index] ?? 0;
            if (opacity === 0) return; // Don't render invisible entries

            const el = document.createElement('div');
            el.className = 'cf-entry cf-' + entry.type;
            el.style.opacity = opacity;
            el.dataset.id = entry.id;

            // Dot prefix
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
                // Animated dots
                const dotsSpan = document.createElement('span');
                dotsSpan.className = 'cf-thinking-dots';
                for (let i = 0; i < 5; i++) {
                    const d = document.createElement('span');
                    d.textContent = '\u25CF'; // ●
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

                // Processing time badge
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

                // Truncation indicator
                if (!entry.expanded && entry.lines.length > COLLAPSE_LINES) {
                    const more = document.createElement('div');
                    more.className = 'cf-more';
                    more.textContent = '\u2026 +' + (entry.lines.length - COLLAPSE_LINES) + ' lines (hover to expand)';
                    linesContainer.appendChild(more);
                }

                el.appendChild(linesContainer);

                // Hover to expand/collapse
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
    }

    function getDot(type) {
        switch (type) {
            case 'action': return '\u23FA';   // ⏺
            case 'thinking': return '\u273B'; // ✻
            case 'success': return '\u2713';  // ✓
            case 'error': return '\u2717';    // ✗
            case 'substep': return '\u23BF';  // ⎿
            default: return '\u23FA';
        }
    }

    function getDotColor(type) {
        switch (type) {
            case 'action': return '#00d4ff';
            case 'thinking': return '#ffaa00';
            case 'success': return '#00ff88';
            case 'error': return '#ff4444';
            case 'substep': return '#888';
            default: return '#00d4ff';
        }
    }

    // ─── Event Wiring ──────────────────────────────────

    // Track services used per command for history
    let currentServicesUsed = [];

    window.addEventListener('nex:system.ready', () => {
        addEntry('success', 'All systems ready', []);
    });

    window.addEventListener('nex:mic.transcribed', (e) => {
        const text = e.detail.text || '';
        commandStartTime = Date.now();
        currentServicesUsed = ['stt'];
        addEntry('action', 'Nex(' + truncate(text, 40) + ')', []);
        showThinking('Thinking...');
    });

    window.addEventListener('nex:user.command', (e) => {
        const text = e.detail.text || '';
        commandStartTime = Date.now();
        currentServicesUsed = [];
        addEntry('action', 'Nex(' + truncate(text, 40) + ')', []);
        showThinking('Thinking...');
    });

    window.addEventListener('nex:tool.executing', (e) => {
        const name = (e.detail.name || 'tool').replace(/_/g, ' ');
        currentServicesUsed.push(e.detail.name || 'tool');
        if (activeThinking) {
            removeEntry(activeThinking);
        }
        activeThinking = addEntry('thinking', 'Running ' + name + '...', []);
    });

    window.addEventListener('nex:command.response', (e) => {
        const text = e.detail.text || '';
        const command = e.detail.command || '';

        // Skip internal commands
        if (command.startsWith('_')) return;

        const elapsed = commandStartTime ? Date.now() - commandStartTime : null;
        commandStartTime = null;

        // Split long responses into lines
        const lines = text.split('\n').filter(l => l.trim());
        const title = lines.length > 0 ? truncate(lines[0], 60) : 'Response delivered';
        const subLines = lines.length > 1 ? lines.slice(1) : [];

        addEntry('action', 'Response \u2014 ' + title, subLines, elapsed);

        // Dispatch to history system
        window.dispatchEvent(new CustomEvent('nex:conversation.complete', {
            detail: {
                userPrompt: command,
                nexResponse: text,
                processingTimeMs: elapsed,
                servicesUsed: [...currentServicesUsed, 'tts'],
            }
        }));
        currentServicesUsed = [];
    });

    function truncate(s, max) {
        return s.length > max ? s.slice(0, max) + '\u2026' : s;
    }

    // ─── Visibility Control ────────────────────────────

    // Show feed on dashboard and orb views
    window.addEventListener('nex:viewchange', (e) => {
        const view = e.detail.view;
        feed.classList.toggle('visible', view === 'dashboard' || view === 'orb');
    });

    // Default visible on orb
    feed.classList.add('visible');

    // Expose for external use
    window.NexConversation = { addEntry, showThinking };
})();
