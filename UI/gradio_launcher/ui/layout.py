import gradio as gr

import celery_client
import db
import styles
import telemetry
import templates
import ui.handlers as handlers


def build_layout() -> gr.Blocks:
    """Builds and returns the complete unified Gradio Blocks layout."""
    with gr.Blocks(title="Invoker Launcher", theme=styles._THEME, css=styles._CSS_MODERN) as demo:
        status_timer = gr.Timer(2)

        gr.HTML(
            f"""
            <div id="app-header">
                <h1>🚀 Invoker Launcher</h1>
                <p>Train YOLO on this GPU node • Config persisted in Redis •
                   Real-time automatic monitoring</p>
                <p id="app-version">v{celery_client.GRADIO_VERSION}</p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); border: 2px solid #3b82f6;
                        border-radius: 12px; padding: 1.2rem 1rem; margin-bottom: 1rem;
                        text-align: center; box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);">
                <span style="font-size: 1.1rem; color: #94a3b8; font-weight: 600;
                             text-transform: uppercase; letter-spacing: 0.05em;">
                    🎯 Target queue (this node):
                </span>
                <span style="font-size: 1.8rem; color: #60a5fa; font-weight: 900;
                             margin-left: 0.75rem; text-shadow: 0 0 10px rgba(96, 165, 250, 0.5);
                             font-family: monospace;">{celery_client._PRIVATE_QUEUE}</span>
            </div>
            """
        )

        gr.Markdown(celery_client.check_redis_connection)

        with gr.Tabs() as tabs:

            # ============================================================
            # TRAINING TAB
            # ============================================================
            with gr.Tab("🚀 Training", id="training_tab"):

                gr.Markdown(
                    "**1.** Choose an example, upload your YAML, or load a saved template  \n"
                    "**2.** Click **🚀 Train**  \n"
                    "**3.** You are taken to *Monitoring* automatically with the Task ID already copied."
                )

                with gr.Row():
                    mode_radio = gr.Radio(
                        choices=[
                            ("✨ Use example", "example"),
                            ("📤 Upload YAML", "upload"),
                            ("📚 My templates", "saved"),
                        ],
                        value="example",
                        label="How would you like to prepare your configuration?",
                        elem_classes=["mode-selector"],
                        container=False,
                    )

                with gr.Column(visible=True) as editor_col:
                    with gr.Group(elem_classes=["mode-card"]):
                        with gr.Row():
                            gr.Markdown("### 📄 YAML Configuration")
                            with gr.Row(elem_id="quick-templates-bar"):
                                btn_cls = gr.Button("🟢 Classification", size="sm", variant="secondary")
                                btn_det = gr.Button("🔵 Detection", size="sm", variant="secondary")
                                btn_seg = gr.Button("🔴 Segmentation", size="sm", variant="secondary")

                        yaml_editor = gr.Code(
                            value=templates.load_template,
                            label="YAML Editor",
                            language="yaml",
                            lines=20,
                            interactive=True,
                            elem_id="yaml-editor",
                        )

                        with gr.Row():
                            gr.Markdown(
                                f"⚙️ **Mode:** "
                                f"`{'Full Pipeline (EDA + Optuna + LLM)' if celery_client.RUN_FULL_PIPELINE else 'Direct Executor Run'}`"
                                f" &nbsp;·&nbsp; 🎯 **Target queue:** `{celery_client._PRIVATE_QUEUE}`"
                            )

                with gr.Column(visible=False) as upload_col:
                    with gr.Group(elem_classes=["mode-card"]):
                        gr.Markdown("### 📤 Upload YAML Configuration")

                        yaml_file = gr.File(
                            label="Select .yaml / .yml file",
                            file_types=[".yaml", ".yml"],
                            file_count="single",
                            elem_id="yaml-upload",
                        )

                        gr.Code(
                            label="Preview",
                            language="yaml",
                            lines=10,
                            interactive=False,
                            elem_id="upload-preview",
                        )

                with gr.Column(visible=False) as saved_col:
                    with gr.Group(elem_classes=["mode-card"]):
                        gr.Markdown("### 📚 My Templates")
                        
                        # Load section
                        with gr.Group(elem_classes=["template-section"]):
                            gr.Markdown("#### Load Template")
                            with gr.Row():
                                saved_templates_dropdown = gr.Dropdown(
                                    choices=templates.list_user_templates(),
                                    label="Select a saved template",
                                    scale=3,
                                    allow_custom_value=False,
                                )
                                load_saved_btn = gr.Button(
                                    "📂 Load into Editor", variant="primary", size="lg"
                                )
                                refresh_saved_btn = gr.Button(
                                    "🔄 Refresh", variant="secondary", size="lg"
                                )
                        
                        # Save section
                        with gr.Group(elem_classes=["template-section"]):
                            gr.Markdown("#### Save Current YAML as New Template")
                            with gr.Row():
                                template_name_box = gr.Textbox(
                                    label="Template name",
                                    placeholder="e.g. my_batch_train_v3",
                                    scale=3,
                                )
                                save_btn = gr.Button(
                                    "💾 Save as Template",
                                    variant="secondary",
                                    size="lg",
                                    elem_id="save-btn",
                                )
                        
                        gr.Markdown(
                            "*💡 **Load** opens the template in the editor for review or launch. "
                            "**Save** persists the YAML you are editing under a new name.*"
                        )

                with gr.Group(elem_classes=["mode-card"]):
                    output_msg = gr.Markdown("")

                    with gr.Row():
                        launch_btn = gr.Button(
                            "🚀 Train",
                            variant="primary",
                            size="lg",
                            interactive=False,
                            elem_id="train-btn",
                        )

            # ============================================================
            # MONITORING TAB
            # ============================================================
            with gr.Tab("📊 Monitoring", id="monitoring_tab"):

                gr.Markdown(
                    "Everything updates **automatically** every 2 seconds: task status, "
                    "CPU/RAM/GPU usage, and training plots. "
                    "No manual refresh needed."
                )

                with gr.Row():
                    task_id_box = gr.Textbox(
                        label="Task ID (hidden — auto-filled when Train is clicked)",
                        interactive=False,
                        placeholder="Will be filled automatically when launching a training…",
                        visible=False,
                    )

                hardware_output = gr.HTML(telemetry.get_executor_stats())

                with gr.Row():
                    status_output = gr.HTML(telemetry._idle_status())

                # LLM Analysis Report — full width for prominence
                with gr.Row():
                    llm_output = gr.HTML(telemetry._idle_llm())

                with gr.Row():
                    download_btn = gr.DownloadButton(
                        "📥 Download all results (ZIP)",
                        variant="secondary",
                        size="lg",
                    )

                with gr.Accordion("📈 Training Results", open=True):
                    with gr.Row():
                        results_plot = gr.Image(label="Training Metrics")
                        confusion_matrix_plot = gr.Image(label="Confusion Matrix")

                with gr.Accordion("🖥️ Worker Status (diagnostic)", open=False):
                    gr.Markdown(
                        "*💡 For operators only: verifies the Celery daemon "
                        "on this node is alive (Online), how many trainings "
                        "run in parallel (Concurrency = 1 in production), and which "
                        "tasks are active or queued. Can be ignored in normal use.*"
                    )
                    local_worker_stats = gr.Markdown()

                with gr.Accordion("📊 Optuna Study History", open=False):
                    with gr.Row():
                        study_selector = gr.Dropdown(
                            choices=db.list_optuna_studies(),
                            label="Select a study from DB",
                            interactive=True,
                            allow_custom_value=True,
                        )
                        refresh_studies_btn = gr.Button("🔄 Reload list", scale=0)

                    study_history_output = gr.Markdown(
                        "Select a study above to load its history."
                    )
                    refresh_history_btn = gr.Button("🔄 Refresh history")

        # ── Event wiring ──────────────────────────────────────────────

        # Toggle configuration mode
        mode_radio.change(
            fn=handlers.toggle_mode,
            inputs=[mode_radio],
            outputs=[editor_col, upload_col, saved_col],
        )

        # Handle uploaded config file
        yaml_file.change(
            fn=handlers.handle_upload,
            inputs=[yaml_file],
            outputs=[yaml_editor, output_msg, launch_btn],
        )
        # Force editor column display and update status message
        yaml_file.change(
            fn=lambda f: (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ),
            inputs=[yaml_file],
            outputs=[editor_col, upload_col, saved_col],
        )

        # Editor inputs change validations
        yaml_editor.change(
            fn=handlers._validate_and_update_btn,
            inputs=[yaml_editor],
            outputs=[output_msg, launch_btn],
        )

        # Show custom queue box when "Custom" selected
        # (queue selector removed — requests always go to the private queue)

        # Save template button (named user template + refresh list)
        save_btn.click(
            fn=handlers.save_named_template_with_feedback,
            inputs=[template_name_box, yaml_editor],
            outputs=[output_msg, saved_templates_dropdown],
        )

        # Train submit bindings (handles execution dispatch, ID updates,
        # and auto-switching tab)
        launch_btn.click(
            fn=handlers.handle_train_click,
            inputs=[yaml_editor],
            outputs=[output_msg, task_id_box, tabs],
        )

        # Dry run / Smoke test (hidden until needed — keep for ops)
        dry_run_btn = gr.Button(
            "🧪 Smoke test", size="sm", visible=False, elem_id="dry-run-btn"
        )
        dry_run_btn.click(
            fn=celery_client.launch_dry_run,
            outputs=[output_msg],
        )

        # Results ZIP download trigger (auto-enabled when results exist)
        download_btn.click(
            fn=telemetry.get_results_zip,
            outputs=[download_btn],
        )

        # Timer ticks (hands-free auto-refresh — no manual buttons needed)
        status_timer.tick(
            fn=telemetry.check_task_status,
            inputs=[task_id_box],
            outputs=[status_output, llm_output],
        )

        status_timer.tick(
            fn=telemetry.get_executor_stats,
            outputs=[hardware_output],
        )

        status_timer.tick(
            fn=celery_client.get_local_worker_status,
            outputs=[local_worker_stats],
        )

        # Auto-refresh metric plots on every tick
        status_timer.tick(
            fn=telemetry.get_training_artifacts,
            outputs=[results_plot, confusion_matrix_plot],
        )

        # Shared Redis templates loading
        btn_cls.click(
            fn=lambda: templates.get_template_from_redis(
                "classification", templates._TEMPLATE_CLS
            ),
            outputs=[yaml_editor],
        )

        btn_det.click(
            fn=lambda: templates.get_template_from_redis(
                "detection", templates._TEMPLATE_DET
            ),
            outputs=[yaml_editor],
        )

        btn_seg.click(
            fn=lambda: templates.get_template_from_redis(
                "segmentation", templates._TEMPLATE_SEG
            ),
            outputs=[yaml_editor],
        )

        # User-saved templates: save with name, load selection, refresh list
        load_saved_btn.click(
            fn=handlers.load_selected_template,
            inputs=[saved_templates_dropdown],
            outputs=[yaml_editor],
        )
        # Loading a template also jumps back to the editor view
        load_saved_btn.click(
            fn=lambda: handlers.toggle_mode("example"),
            outputs=[editor_col, upload_col, saved_col],
        )

        refresh_saved_btn.click(
            fn=lambda: gr.update(
                choices=templates.list_user_templates(),
                value=None,
            ),
            outputs=[saved_templates_dropdown],
        )

        # Optuna study history manual refreshes
        refresh_studies_btn.click(
            fn=lambda: gr.update(choices=db.list_optuna_studies()),
            outputs=[study_selector],
        )

        refresh_history_btn.click(
            fn=db.get_optuna_study_history,
            inputs=[study_selector],
            outputs=[study_history_output],
        )

        # Automatically load worker status on page load
        demo.load(
            fn=celery_client.get_local_worker_status,
            outputs=[local_worker_stats],
        )

    return demo
