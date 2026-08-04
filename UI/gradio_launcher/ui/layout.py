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
                <h1>🚀 Invoker Launcher
                    <span style="font-size: 1.2rem; opacity: 0.7; font-weight: 400;">
                        (Gradio UI {celery_client.GRADIO_VERSION})
                    </span>
                </h1>
                <p>Entrena YOLO en este nodo GPU • Configuración persistida en Redis •
                   Monitorización automática en tiempo real</p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); border: 2px solid #3b82f6;
                        border-radius: 12px; padding: 1.2rem 1rem; margin-bottom: 1rem;
                        text-align: center; box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);">
                <span style="font-size: 1.1rem; color: #94a3b8; font-weight: 600;
                             text-transform: uppercase; letter-spacing: 0.05em;">
                    🎯 Cola destino (este nodo):
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
                    "**1.** Elige un ejemplo, sube tu YAML o carga un template guardado → "
                    "**2.** Pulsa **🚀 Train** → "
                    "**3.** Se te lleva a *Monitoring* automáticamente con el Task ID ya copiado."
                )

                with gr.Row():
                    mode_radio = gr.Radio(
                        choices=[
                            ("✨ Usar ejemplo", "example"),
                            ("📤 Subir YAML", "upload"),
                            ("📚 Mis templates", "saved"),
                        ],
                        value="example",
                        label="¿Cómo quieres preparar tu configuración?",
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
                                f"⚙️ **Modo:** "
                                f"`{'Full Pipeline (EDA + Optuna + LLM)' if celery_client.RUN_FULL_PIPELINE else 'Direct Executor Run'}`"
                                f" &nbsp;·&nbsp; 🎯 **Cola destino:** `{celery_client._PRIVATE_QUEUE}`"
                            )

                with gr.Column(visible=False) as upload_col:
                    with gr.Group(elem_classes=["mode-card"]):
                        gr.Markdown("### 📤 Subir configuración YAML")

                        yaml_file = gr.File(
                            label="Selecciona archivo .yaml / .yml",
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
                        gr.Markdown("### 📚 Mis templates")
                        with gr.Row():
                            saved_templates_dropdown = gr.Dropdown(
                                choices=templates.list_user_templates(),
                                label="Template guardado",
                                scale=3,
                                allow_custom_value=False,
                            )
                            load_saved_btn = gr.Button(
                                "📂 Cargar", variant="secondary", size="lg"
                            )
                            refresh_saved_btn = gr.Button(
                                "🔄", variant="secondary", size="lg"
                            )
                        with gr.Row():
                            template_name_box = gr.Textbox(
                                label="Guardar el YAML actual como…",
                                placeholder="ej. mi_entreno_batch_v3",
                                scale=3,
                            )
                            save_btn = gr.Button(
                                "💾 Guardar template",
                                variant="secondary",
                                size="lg",
                                elem_id="save-btn",
                            )
                        gr.Markdown(
                            "*💡 **Cargar** abre el template en el editor para revisarlo o lanzarlo; "
                            "**Guardar** persiste el YAML que estés editando bajo ese nombre.*"
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
                    "Todo se actualiza **solo** cada 2 segundos: estado de la tarea, "
                    "consumo de CPU/RAM/GPU y las gráficas de entrenamiento. "
                    "No hace falta pulsar nada."
                )

                with gr.Row():
                    task_id_box = gr.Textbox(
                        label="Task ID (oculto — se rellena automáticamente al pulsar Train)",
                        interactive=False,
                        placeholder="Se rellenará solo al lanzar un entrenamiento…",
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
                        "📥 Descargar todos los resultados (ZIP)",
                        variant="secondary",
                        size="lg",
                    )

                with gr.Accordion("📈 Resultados del entrenamiento", open=True):
                    with gr.Row():
                        results_plot = gr.Image(label="Training Metrics")
                        confusion_matrix_plot = gr.Image(label="Confusion Matrix")

                with gr.Accordion("🖥️ Estado del worker (diagnóstico)", open=False):
                    gr.Markdown(
                        "*💡 Esto es solo para operadores: verifica que el daemon "
                        "Celery de este nodo está vivo (Online), cuántos entrenamientos "
                        "ejecuta en paralelo (Concurrency = 1 en producción) y qué "
                        "tareas están activas o en cola. En uso normal puedes ignorarlo.*"
                    )
                    local_worker_stats = gr.Markdown()

                with gr.Accordion("📊 Historial de estudios Optuna", open=False):
                    with gr.Row():
                        study_selector = gr.Dropdown(
                            choices=db.list_optuna_studies(),
                            label="Selecciona un estudio de la BD",
                            interactive=True,
                            allow_custom_value=True,
                        )
                        refresh_studies_btn = gr.Button("🔄 Recargar lista", scale=0)

                    study_history_output = gr.Markdown(
                        "Selecciona un estudio arriba para cargar su historial."
                    )
                    refresh_history_btn = gr.Button("🔄 Refrescar historial")

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
