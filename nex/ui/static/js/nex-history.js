/**
 * NEX History — Prompt history drawer with search, replay, and keyboard shortcut.
 */

(() => {
    const drawer = document.getElementById('history-drawer');
    const backdrop = document.getElementById('history-backdrop');
    const closeBtn = document.getElementById('history-close');
    const searchInput = document.getElementById('history-search-input');
    const listEl = document.getElementById('history-list');
    const statsEl = document.getElementById('history-stats');
    const clearBtn = document.getElementById('history-clear');
    const toggleBtn = document.getElementById('history-toggle-btn');

    let historyData = [];

    // ─── Always-visible sidebar — load on init ──────────

    // Load history immediately (sidebar is always visible)
    loadHistory();

    // ─── Load History ──────────────────────────────────

    async function loadHistory() {
        try {
            const resp = await fetch('/api/history');
            const data = await resp.json();
            historyData = data.entries || [];
            const fileSize = data.fileSizeBytes || 0;
            updateStats(historyData.length, fileSize);
            renderList(historyData);
        } catch (e) {
            listEl.innerHTML = '<div class="history-empty">Failed to load history</div>';
        }
    }

    function updateStats(count, bytes) {
        const kb = (bytes / 1024).toFixed(0);
        statsEl.textContent = count > 0
            ? `Showing ${count} of ${count}  \u2022  Memory: ${kb}KB / 500KB`
            : 'No history';
    }

    // ─── Render ────────────────────────────────────────

    function renderList(entries) {
        if (!listEl) return;
        listEl.innerHTML = '';

        if (entries.length === 0) {
            listEl.innerHTML = '<div class="history-empty">No conversations yet</div>';
            return;
        }

        // Group by date
        const groups = groupByDate(entries.slice().reverse()); // newest first
        for (const [label, items] of groups) {
            const dateLabel = document.createElement('div');
            dateLabel.className = 'history-date-label';
            dateLabel.textContent = label;
            listEl.appendChild(dateLabel);

            for (const item of items) {
                listEl.appendChild(createHistoryItem(item));
            }
        }
    }

    function groupByDate(entries) {
        const groups = new Map();
        const now = new Date();
        const today = dateKey(now);
        const yesterday = dateKey(new Date(now.getTime() - 86400000));

        for (const entry of entries) {
            const d = new Date(entry.timestamp);
            const key = dateKey(d);
            let label;
            if (key === today) label = 'TODAY';
            else if (key === yesterday) label = 'YESTERDAY';
            else label = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase();

            if (!groups.has(label)) groups.set(label, []);
            groups.get(label).push(entry);
        }
        return groups;
    }

    function dateKey(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    function createHistoryItem(entry) {
        const el = document.createElement('div');
        el.className = 'history-item';

        const d = new Date(entry.timestamp);
        const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const prompt = truncate(entry.userPrompt || '', 60);
        const response = truncate(entry.nexResponse || '', 80);

        el.innerHTML = `
            <div class="history-item-header">
                <span class="history-item-time">${escHtml(time)}</span>
                <button class="history-item-replay" title="Replay via TTS">\u25B6</button>
            </div>
            <div class="history-item-prompt">"${escHtml(prompt)}"</div>
            <div class="history-item-response">${escHtml(response)}</div>
        `;

        // Click to expand/collapse
        el.addEventListener('click', (e) => {
            if (e.target.closest('.history-item-replay')) return;
            el.classList.toggle('expanded');
            if (el.classList.contains('expanded')) {
                el.querySelector('.history-item-prompt').textContent = '"' + (entry.userPrompt || '') + '"';
                el.querySelector('.history-item-response').textContent = entry.nexResponse || '';
            } else {
                el.querySelector('.history-item-prompt').textContent = '"' + prompt + '"';
                el.querySelector('.history-item-response').textContent = response;
            }
        });

        // Replay button — send response text via TTS
        el.querySelector('.history-item-replay').addEventListener('click', (e) => {
            e.stopPropagation();
            replayTTS(entry.nexResponse || '');
        });

        return el;
    }

    // ─── Search ────────────────────────────────────────

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const q = searchInput.value.toLowerCase().trim();
            if (!q) {
                renderList(historyData);
                return;
            }
            const filtered = historyData.filter(e =>
                (e.userPrompt || '').toLowerCase().includes(q) ||
                (e.nexResponse || '').toLowerCase().includes(q)
            );
            renderList(filtered);
        });
    }

    // ─── Clear All ─────────────────────────────────────

    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (!confirm('Clear all prompt history?')) return;
            try {
                await fetch('/api/history', { method: 'DELETE' });
                historyData = [];
                renderList([]);
                updateStats(0, 0);
            } catch (e) {
                console.error('Failed to clear history:', e);
            }
        });
    }

    // ─── Replay TTS ────────────────────────────────────

    function replayTTS(text) {
        if (!text) return;
        // Send as a command response to trigger TTS via the WebSocket
        const ws = window._nexWs;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'replay_tts', text: text }));
        }
    }

    // ─── Save Conversations ────────────────────────────

    window.addEventListener('nex:conversation.complete', async (e) => {
        const { userPrompt, nexResponse, processingTimeMs, servicesUsed } = e.detail;
        if (!userPrompt && !nexResponse) return;
        try {
            await fetch('/api/history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    userPrompt,
                    nexResponse,
                    processingTimeMs,
                    servicesUsed,
                }),
            });
            // Auto-refresh the sidebar
            loadHistory();
        } catch (e) {
            console.error('Failed to save history entry:', e);
        }
    });

    // ─── Helpers ───────────────────────────────────────

    function truncate(s, max) {
        return s.length > max ? s.slice(0, max) + '\u2026' : s;
    }

    function escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }
})();
