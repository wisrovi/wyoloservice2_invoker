import gradio as gr

# UI Colors & Layout theme
_THEME = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="gray",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)

# Custom Glassmorphic Dark Style Sheet
_CSS_MODERN: str = """
/* General container & page background styling */
body {
    background-color: #0b0f19 !important;
}

.gradio-container {
    background-color: #0b0f19 !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* Stunning Glassmorphic header */
#app-header {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #9333ea 100%) !important;
    color: white !important;
    padding: 2.5rem 2rem !important;
    margin-bottom: 2rem !important;
    text-align: center !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 30px rgba(124, 58, 237, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

#app-header h1 {
    font-size: 2.8rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.05em !important;
    text-shadow: 0 4px 10px rgba(0,0,0,0.2) !important;
    margin-bottom: 0.5rem !important;
}

#app-header p {
    font-size: 1.1rem !important;
    opacity: 0.9 !important;
    font-weight: 500 !important;
}

/* Beautiful custom tabs */
.tabs {
    border-bottom: 2px solid #1e293b !important;
}

.tab-nav button {
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.75rem 1.5rem !important;
    transition: all 0.3s ease !important;
    color: #94a3b8 !important;
}

.tab-nav button.selected {
    color: #818cf8 !important;
    border-bottom: 3px solid #6366f1 !important;
}

/* Cards & Accordions Glassmorphic design */
.gr-box, .gr-panel, .gr-form, .gr-block, .gr-row, .gr-group {
    background-color: #111827 !important;
    border: 1px solid #1f2937 !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    margin-bottom: 1rem !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
}

/* Inputs & Textareas styling */
input, textarea, select, .gr-input {
    background-color: #1f2937 !important;
    color: #f3f4f6 !important;
    border: 1px solid #374151 !important;
    border-radius: 8px !important;
    padding: 0.75rem !important;
    font-size: 0.95rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}

input:focus, textarea:focus, select:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.3) !important;
    outline: none !important;
}

/* Neon buttons */
button.primary, #train-btn {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 1.5rem !important;
    font-size: 1.05rem !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4) !important;
}

button.primary:hover, #train-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.6) !important;
}

button.secondary, #save-btn, #check-btn, #refresh-btn {
    background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 1.5rem !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4) !important;
}

button.secondary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.6) !important;
}

/* Accordions modern design */
details.gr-accordion {
    border: 1px solid #1f2937 !important;
    background-color: #111827 !important;
    border-radius: 12px !important;
    margin-bottom: 1rem !important;
}

details.gr-accordion summary {
    font-weight: 700 !important;
    color: #e5e7eb !important;
    padding: 1rem !important;
    font-size: 1.1rem !important;
    border-bottom: 1px solid #1f2937 !important;
    cursor: pointer !important;
}

/* Optuna and Telemetry Markdown tables styling */
table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 1.5rem 0 !important;
    font-size: 0.95rem !important;
    color: #d1d5db !important;
}

th {
    background-color: #1f2937 !important;
    color: #f3f4f6 !important;
    font-weight: 700 !important;
    text-align: left !important;
    padding: 0.75rem 1rem !important;
    border-bottom: 2px solid #374151 !important;
}

td {
    padding: 0.75rem 1rem !important;
    border-bottom: 1px solid #1f2937 !important;
}

tr:nth-child(even) {
    background-color: #111827 !important;
}

tr:hover {
    background-color: #1f2937 !important;
}

#quick-templates-bar {
    justify-content: flex-end;
    gap: 5px;
}

/* Semi-hidden dry-run button */
#dry-run-btn {
    opacity: 0.15 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 4px !important;
    font-size: 0.8rem !important;
    min-width: 20px !important;
    width: 20px !important;
    transition: opacity 0.2s ease !important;
}
#dry-run-btn:hover { opacity: 0.6 !important; }

/* ── Resource consumption dashboard ─────────────────────────────── */
.res-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin: 0.5rem 0 0.25rem 0;
}

.res-card {
    position: relative !important;
    background: linear-gradient(165deg, #16233d 0%, #0d1526 60%, #0a1120 100%) !important;
    border: 1px solid #2b3c5e !important;
    border-radius: 16px !important;
    padding: 1.1rem 1rem !important;
    text-align: center !important;
    box-shadow:
        0 6px 18px rgba(0, 0, 0, 0.45),
        inset 0 1px 0 rgba(148, 163, 184, 0.12) !important;
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
    overflow: hidden !important;
}

.res-card::before {
    content: "" !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: 3px !important;
    background: linear-gradient(90deg, #60a5fa, #818cf8, #a78bfa) !important;
    opacity: 0.85 !important;
    border-radius: 16px 16px 0 0 !important;
}

.res-card:hover {
    transform: translateY(-4px) !important;
    border-color: #6366f1 !important;
    box-shadow:
        0 10px 26px rgba(99, 102, 241, 0.25),
        inset 0 1px 0 rgba(148, 163, 184, 0.12) !important;
}

.res-icon {
    font-size: 1.7rem !important;
    margin-bottom: 0.3rem !important;
    filter: drop-shadow(0 2px 6px rgba(96, 165, 250, 0.35)) !important;
}

.res-label {
    font-size: 0.72rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: #7d8fb3 !important;
    font-weight: 700 !important;
    margin-bottom: 0.15rem !important;
}

.res-value {
    font-size: 1.6rem !important;
    font-weight: 800 !important;
    color: #f1f5f9 !important;
    font-family: 'JetBrains Mono', monospace !important;
    margin: 0.2rem 0 0.55rem 0 !important;
    text-shadow: 0 0 14px rgba(96, 165, 250, 0.25) !important;
}

.res-wait {
    color: #64748b !important;
    font-size: 0.9rem !important;
    text-align: center !important;
    margin-top: 0.75rem !important;
}

.bar {
    width: 100% !important;
    height: 7px !important;
    background: #1e293b !important;
    border-radius: 999px !important;
    overflow: hidden !important;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.5) !important;
}

.bar-fill {
    height: 100% !important;
    border-radius: 999px !important;
    transition: width 0.6s ease !important;
    box-shadow: 0 0 8px currentColor !important;
}

/* ── Task status card ───────────────────────────────────────────── */
.status-card {
    background: linear-gradient(160deg, #1e293b 0%, #0f172a 100%) !important;
    border: 1px solid #334155 !important;
    border-radius: 12px !important;
    padding: 1rem 1.1rem !important;
    display: flex !important;
    gap: 1rem !important;
    align-items: flex-start !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35) !important;
    height: 100% !important;
}

.status-pill {
    min-width: 2.6rem !important;
    height: 2.6rem !important;
    border-radius: 10px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 1.4rem !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
}

.status-body {
    flex: 1 !important;
    color: #cbd5e1 !important;
    font-size: 0.95rem !important;
    line-height: 1.5 !important;
}

.status-title {
    font-size: 1.05rem !important;
    margin-bottom: 0.35rem !important;
}

.status-body code {
    background: #0b0f19 !important;
    border: 1px solid #334155 !important;
    border-radius: 6px !important;
    padding: 0.1rem 0.4rem !important;
    font-size: 0.85rem !important;
    color: #93c5fd !important;
}

/* ── LLM analysis states ────────────────────────────────────────── */
.llm-state {
    background: linear-gradient(160deg, #1e293b 0%, #0f172a 100%) !important;
    border: 2px dashed #475569 !important;
    border-radius: 16px !important;
    padding: 1.25rem 1.5rem !important;
    color: #94a3b8 !important;
    font-size: 1rem !important;
    line-height: 1.65 !important;
    box-shadow:
        0 6px 20px rgba(0, 0, 0, 0.45),
        inset 0 1px 0 rgba(148, 163, 184, 0.08) !important;
    height: 100% !important;
    transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}

.llm-state b { color: #f1f5f9 !important; }

.llm-done {
    border-style: solid !important;
    border-color: #10b981 !important;
    box-shadow:
        0 6px 24px rgba(16, 185, 129, 0.18),
        0 0 0 1px rgba(16, 185, 129, 0.25),
        inset 0 1px 0 rgba(16, 185, 129, 0.12) !important;
}

.llm-error {
    border-style: solid !important;
    border-color: #ef4444 !important;
    box-shadow:
        0 6px 24px rgba(239, 68, 68, 0.18),
        0 0 0 1px rgba(239, 68, 68, 0.25),
        inset 0 1px 0 rgba(239, 68, 68, 0.12) !important;
}

.llm-report {
    margin-top: 0.75rem !important;
    color: #e2e8f0 !important;
    max-height: 320px !important;
    overflow-y: auto !important;
    white-space: pre-wrap !important;
    font-size: 0.95rem !important;
    line-height: 1.7 !important;
    background: rgba(15, 23, 42, 0.6) !important;
    border-radius: 10px !important;
    padding: 1rem !important;
    border: 1px solid #334155 !important;
}

/* ── Execution mode / queue selectors ───────────────────────────── */
.mode-card textarea, .mode-card input { font-family: 'JetBrains Mono', monospace !important; }
"""

# JS script for keyboard shortcuts
_JS_SHORTCUTS: str = """
<script>
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        var btn = document.getElementById('train-btn');
        if (btn) btn.click();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        var btn = document.getElementById('save-btn');
        if (btn) btn.click();
    }
});
</script>
"""
