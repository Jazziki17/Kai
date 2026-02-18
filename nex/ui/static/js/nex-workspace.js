/**
 * NEX WORKSPACE — Tool output pane with auto-show/hide.
 * Auto-opens when tools execute, fills output, auto-hides after 15s.
 */

(() => {
    const pane = document.getElementById('workspace-pane');
    const output = document.getElementById('workspace-output');
    const pinBtn = document.getElementById('workspace-pin');
    const closeBtn = document.getElementById('workspace-close');
    const toggleBtn = document.getElementById('workspace-toggle-btn');

    let pinned = false;
    let autoHideTimer = null;
    let blockCount = 0;
    const MAX_BLOCKS = 50;

    // Only auto-open workspace for these file/terminal tools
    const WORKSPACE_TOOLS = new Set([
        'run_shell_command', 'create_file', 'read_file',
        'list_directory', 'search_files', 'fetch_webpage',
    ]);

    function open() {
        if (!pane.classList.contains('open')) {
            if (window.NexSounds) window.NexSounds.play('workspaceSlide');
        }
        pane.classList.add('open');
        document.body.classList.add('workspace-open');
        window.dispatchEvent(new CustomEvent('nex:workspace.toggle'));
    }

    function close() {
        if (pane.classList.contains('open')) {
            if (window.NexSounds) window.NexSounds.play('workspaceSlide');
        }
        pane.classList.remove('open');
        document.body.classList.remove('workspace-open');
        clearAutoHide();
        window.dispatchEvent(new CustomEvent('nex:workspace.toggle'));
    }

    function toggle() {
        if (pane.classList.contains('open')) {
            close();
        } else {
            open();
        }
    }

    function clearAutoHide() {
        if (autoHideTimer) {
            clearTimeout(autoHideTimer);
            autoHideTimer = null;
        }
    }

    function startAutoHide() {
        if (pinned) return;
        clearAutoHide();
        autoHideTimer = setTimeout(close, 15000);
    }

    function trimBlocks() {
        while (output.children.length > MAX_BLOCKS) {
            output.removeChild(output.firstChild);
        }
    }

    function scrollToBottom() {
        output.scrollTop = output.scrollHeight;
    }

    function getToolBlock(toolName) {
        // Find the last block for this tool that is still running
        const blocks = output.querySelectorAll('.ws-tool-block');
        for (let i = blocks.length - 1; i >= 0; i--) {
            if (blocks[i].dataset.tool === toolName) {
                const badge = blocks[i].querySelector('.ws-tool-badge');
                if (badge && badge.classList.contains('running')) {
                    return blocks[i];
                }
            }
        }
        return null;
    }

    // Tool executing: create block with RUNNING badge (only auto-open for file/terminal tools)
    window.addEventListener('nex:tool.executing', (e) => {
        const { name } = e.detail || {};
        if (!name) return;

        // Only auto-open for file/terminal tools
        if (WORKSPACE_TOOLS.has(name)) {
            clearAutoHide();
            open();
        }

        const block = document.createElement('div');
        block.className = 'ws-tool-block';
        block.dataset.tool = name;
        block.innerHTML = `
            <div class="ws-tool-header">
                <span class="ws-tool-name">${escapeHtml(name.replace(/_/g, ' '))}</span>
                <span class="ws-tool-badge running">RUNNING</span>
            </div>
            <div class="ws-tool-result" style="color: rgba(255,255,255,0.25); font-style: italic;">Executing...</div>
        `;

        output.appendChild(block);
        blockCount++;
        trimBlocks();
        scrollToBottom();
    });

    // Tool output: fill in args + result
    window.addEventListener('nex:tool.output', (e) => {
        const { name, output: toolOutput, args } = e.detail || {};
        if (!name) return;

        const block = getToolBlock(name);
        if (!block) return;

        // Build args display
        let argsHtml = '';
        if (args && Object.keys(args).length > 0) {
            const argParts = Object.entries(args).map(([k, v]) =>
                `<span>${escapeHtml(k)}</span>: ${escapeHtml(String(v))}`
            );
            argsHtml = `<div class="ws-tool-args">${argParts.join(', ')}</div>`;
        }

        // Replace the placeholder result
        const resultEl = block.querySelector('.ws-tool-result');
        if (resultEl) {
            resultEl.style.color = '';
            resultEl.style.fontStyle = '';
            resultEl.textContent = toolOutput || '(no output)';
        }

        // Insert args before result
        if (argsHtml) {
            const headerEl = block.querySelector('.ws-tool-header');
            if (headerEl && !block.querySelector('.ws-tool-args')) {
                headerEl.insertAdjacentHTML('afterend', argsHtml);
            }
        }

        scrollToBottom();
    });

    // Tool completed: update badge, start auto-hide
    window.addEventListener('nex:tool.completed', (e) => {
        const { name, success } = e.detail || {};
        if (!name) return;

        const block = getToolBlock(name);
        if (block) {
            const badge = block.querySelector('.ws-tool-badge');
            if (badge) {
                badge.classList.remove('running');
                if (success) {
                    badge.classList.add('done');
                    badge.textContent = 'DONE';
                } else {
                    badge.classList.add('error');
                    badge.textContent = 'ERROR';
                }
            }
        }

        startAutoHide();
    });

    // Pin button
    if (pinBtn) {
        pinBtn.addEventListener('click', () => {
            pinned = !pinned;
            pinBtn.classList.toggle('pinned', pinned);
            if (pinned) {
                clearAutoHide();
            }
        });
    }

    // Close button
    if (closeBtn) {
        closeBtn.addEventListener('click', close);
    }

    // Sidebar toggle button
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggle);
    }

    // Keyboard shortcut: Ctrl+`
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === '`') {
            e.preventDefault();
            toggle();
        }
    });

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
})();
