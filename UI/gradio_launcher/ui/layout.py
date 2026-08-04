import gradio as gr
import celery_client
import templates
import db
import telemetry
import styles
import ui.handlers as handlers

def build_layout() -> gr.Blocks:
    """Builds and returns the complete unified Gradio Blocks layout."""
    
    with gr.Blocks(title="Invoker Launcher", theme=styles._THEME, css=styles._CSS_MODERN) as demo:
        status_timer = gr.Timer(2)

        gr.HTML(
            f"""
            <div id="app-header">
                <h1>🚀 Invoker Launcher <span style="font-size: 1.2rem; opacity: 0.7; font-weight: 400;">(Gradio UI {celery_client.GRADIO_VERSION})</span></h1>
                <p>
                    Direct training submission to local GPU invoker • 
                    Redis-persisted configs • 
                    Queue-aware dispatch
                </p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); border: 2px solid #3b82f6; border-radius: 12px; padding: 1.2rem 1rem; margin-bottom: 1.5rem; text-align: center; box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);">
                <span style="font-size: 1.1rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">🎯 Active Destination Queue (Cola Destino):</span>
                <span style="font-size: 1.8rem; color: #60a5fa; font-weight: 900; margin-left: 0.75rem; text-shadow: 0 0 10px rgba(96, 165, 250, 0.5); font-family: monospace;">{celery_client._PRIVATE_QUEUE}</span>
            </div>
            """
        )

        status_bar = gr.Markdown(celery_client.check_redis_connection)

        with gr.Tabs():

            # ============================================================
            # TRAINING TAB
            # ============================================================
            with gr.Tab("🚀 Training"):

                with gr.Row():
                    mode_radio = gr.Radio(
                        choices=[("✏️ Edit YAML", "edit"), ("📤 Upload .yaml", "upload")],
                        value="edit",
                        label="Configuration Mode",
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
                            lines=22,
                            interactive=True,
                            elem_id="yaml-editor",
                        )

                        with gr.Row():
                            save_btn = gr.Button(
                                "💾 Save Template",
                                variant="secondary",
                                size="sm",
                                elem_id="save-btn",
                            )

                            clear_btn = gr.Button(
                                "🗑 Clear",
                                variant="secondary",
                                size="sm",
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

                        upload_preview = gr.Code(
                            label="Preview",
                            language="yaml",
                            lines=12,
                            interactive=False,
                            elem_id="upload-preview",
                        )

                with gr.Group(elem_classes=["mode-card"]):
                    gr.Markdown("### ⚙️ Dispatch Parameters")
                    output_msg = gr.Markdown("")

                    with gr.Row():
                        launch_btn = gr.Button(
                            "🔥 Train",
                            variant="primary",
                            size="lg",
                            interactive=False,
                            elem_id="train-btn",
                        )

                        dry_run_btn = gr.Button(
                            "🧪",
                            variant="secondary",
                            size="sm",
                            elem_id="dry-run-btn",
                        )

            # ============================================================
            # MONITORING TAB
            # ============================================================
            with gr.Tab("📊 Monitoring"):

                hardware_output = gr.Markdown(telemetry.build_status_table("-", "-", "-", "-"))

                task_id_box = gr.Textbox(
                    label="Task ID",
                    interactive=True,
                    placeholder="Paste task id here...",
                )

                with gr.Row():
                    check_btn = gr.Button(
                        "🔍 Check Status",
                        variant="secondary",
                        size="sm",
                    )

                    refresh_results_btn = gr.Button(
                        "🔄 Refresh Results",
                        size="sm",
                    )

                status_output = gr.Markdown("")

                llm_output = gr.Textbox(
                    label="LLM Analysis",
                    lines=15,
                    interactive=False,
                )

                with gr.Accordion("📈 Training Results", open=True):
                    with gr.Row():
                        results_plot = gr.Image(label="Training Metrics")
                        confusion_matrix_plot = gr.Image(label="Confusion Matrix")

                with gr.Accordion("🖥️ Local Worker Status", open=True):
                    local_worker_stats = gr.Markdown()
                    refresh_worker_btn = gr.Button("🔄 Refresh Worker Status")

                with gr.Accordion("📊 Optuna Study History", open=True):
                    with gr.Row():
                        study_selector = gr.Dropdown(
                            choices=db.list_optuna_studies(),
                            label="Select Study from DB",
                            interactive=True,
                            allow_custom_value=True,
                        )
                        refresh_studies_btn = gr.Button("🔄 Reload Studies List", scale=0)
                    
                    study_history_output = gr.Markdown("Select a study above to load history.")
                    refresh_history_btn = gr.Button("🔄 Refresh Study History")

                with gr.Group(elem_id="executor-section", visible=True):
                    gr.Markdown("### ⚡ Advanced: Direct Executor Run")
                    gr.Markdown(
                        "*Bypasses Celery queue. Writes config to `/home/wyolo/request` "
                        "and launches executor container directly with GPU access.*"
                    )

                    executor_btn = gr.Button(
                        "🚀 Run via Executor",
                        variant="primary",
                        size="lg",
                        elem_id="executor-btn",
                    )

                    executor_output = gr.Markdown("")

        # ── Event wiring ──────────────────────────────────────────────

        # Toggle configuration mode
        mode_radio.change(
            fn=handlers.toggle_mode,
            inputs=[mode_radio],
            outputs=[editor_col, upload_col],
        )

        # Handle uploaded config file
        yaml_file.change(
            fn=handlers.handle_upload,
            inputs=[yaml_file],
            outputs=[yaml_editor, output_msg, launch_btn],
        )
        # Force editor column display and update status message
        yaml_file.change(
            fn=lambda f: (gr.update(visible=True), gr.update(visible=False)),
            inputs=[yaml_file],
            outputs=[editor_col, upload_col],
        )

        # Editor inputs change validations
        yaml_editor.change(
            fn=handlers._validate_and_update_btn,
            inputs=[yaml_editor],
            outputs=[output_msg, launch_btn],
        )

        # Button trigger callbacks
        save_btn.click(
            fn=handlers._save_with_feedback,
            inputs=[yaml_editor],
            outputs=[status_bar],
        )

        clear_btn.click(
            fn=lambda: ("", gr.update(interactive=False)),
            outputs=[output_msg, launch_btn],
        )

        # Train submit bindings
        launch_btn.click(
            fn=celery_client.validate_and_launch,
            inputs=[yaml_editor],
            outputs=[output_msg],
        )

        # Dry run / Smoke test
        dry_run_btn.click(
            fn=celery_client.launch_dry_run,
            outputs=[output_msg],
        )

        # Check Celery task status manually
        check_btn.click(
            fn=telemetry.check_task_status,
            inputs=[task_id_box],
            outputs=[status_output, llm_output],
        )

        # Timer ticks
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

        # Refresh metric plots
        refresh_results_btn.click(
            fn=telemetry.get_training_artifacts,
            outputs=[results_plot, confusion_matrix_plot],
        )

        # Shared Redis templates loading
        btn_cls.click(
            fn=lambda: templates.get_template_from_redis("classification", templates._TEMPLATE_CLS),
            outputs=[yaml_editor],
        )

        btn_det.click(
            fn=lambda: templates.get_template_from_redis("detection", templates._TEMPLATE_DET),
            outputs=[yaml_editor],
        )

        btn_seg.click(
            fn=lambda: templates.get_template_from_redis("segmentation", templates._TEMPLATE_SEG),
            outputs=[yaml_editor],
        )

        # Worker & Optuna manual refreshes
        refresh_worker_btn.click(
            fn=celery_client.get_local_worker_status,
            outputs=[local_worker_stats],
        )

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

        # Direct executor run
        executor_btn.click(
            fn=telemetry.launch_via_executor,
            inputs=[yaml_editor],
            outputs=[executor_output],
        )

    return demo
