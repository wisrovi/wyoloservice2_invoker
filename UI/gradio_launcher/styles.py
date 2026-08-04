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
