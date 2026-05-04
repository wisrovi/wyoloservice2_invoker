import os
import yaml
import json
import gradio as gr
from celery import Celery

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "192.168.1.202")
REDIS_PORT = os.getenv("REDIS_PORT", "23437")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Initialize Celery
celery_app = Celery("gradio_launcher", broker=REDIS_URL, backend=REDIS_URL)

# Paths to default configs (mapped via volumes or relative paths)
CONFIG_BASE_PATH = "/app/examples"
CONFIG_PATHS = {
    "Clasificación": f"{CONFIG_BASE_PATH}/clasificacion/config_train.yaml",
    "Detección": f"{CONFIG_BASE_PATH}/detecion/config_train.yaml",
    "Segmentación": f"{CONFIG_BASE_PATH}/segmentacion/config_train.yaml"
}

def load_yaml_config(task_type):
    path = CONFIG_PATHS.get(task_type)
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def handle_mode_change(is_demo):
    # Returns updates for task_type (visible if demo), data_path (interactive if not demo)
    return (
        gr.update(visible=is_demo),
        gr.update(interactive=not is_demo)
    )

def handle_task_change(task_type, is_demo):
    if not is_demo:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
    config = load_yaml_config(task_type)
    train_cfg = config.get("train", {})
    metadata = config.get("metadata", {})
    
    return (
        config.get("model", ""),
        train_cfg.get("data", ""),
        train_cfg.get("epochs", 2),
        train_cfg.get("imgsz", 640),
        metadata.get("author", "Gradio User"),
        metadata.get("content", "")
    )

def launch_training(task_type, is_demo, model, data, epochs, imgsz, author, description, queue):
    try:
        final_type = task_type if is_demo else "custom"
        payload = {
            "train": {
                "model": model,
                "data": data,
                "epochs": int(epochs),
                "imgsz": int(imgsz),
                "batch": -1
            },
            "metadata": {
                "author": author,
                "content": description,
                "type": final_type.lower(),
                "mode": "demo" if is_demo else "manual"
            },
            "user_id": author
        }
        
        task_name = "tasks.train_on_gpu_simple"
        result = celery_app.send_task(
            task_name,
            args=[payload],
            queue=queue
        )
        
        return f"✅ Tarea enviada con éxito!\n\nID: {result.id}\nModo: {'Demo' if is_demo else 'Manual'}\nCola: {queue}"
    except Exception as e:
        return f"❌ Error al enviar la tarea: {str(e)}"

# --- UI Theme ---
theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="gray",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)

with gr.Blocks(theme=theme, title="NeuralForge Launcher") as demo:
    gr.Markdown("# 🚀 NeuralForge AI Launcher")
    
    with gr.Row():
        with gr.Column(scale=1):
            is_demo = gr.Checkbox(label="🌟 Activar Modo Demo", value=True, info="Pre-carga configuraciones de ejemplo")
            task_type = gr.Dropdown(
                choices=["Clasificación", "Detección", "Segmentación"],
                label="🎯 Ejemplo de Tarea",
                value="Detección",
                visible=True
            )
        
        with gr.Column(scale=2):
            with gr.Group():
                gr.Markdown("### 🛠️ Configuración del Entrenamiento")
                with gr.Row():
                    model = gr.Textbox(label="Modelo Base (.pt)", placeholder="yolov8n.pt")
                    data_path = gr.Textbox(label="Ruta del Dataset", placeholder="/datasets/...", interactive=False)
                
                with gr.Row():
                    epochs = gr.Number(label="Epochs", value=2, precision=0)
                    imgsz = gr.Number(label="Tamaño Imagen", value=640, precision=0)
            
            with gr.Group():
                gr.Markdown("### 📝 Metadatos")
                with gr.Row():
                    author = gr.Textbox(label="Autor", value="Gradio User")
                    queue = gr.Dropdown(
                        choices=["gpus_high", "gpus_medium", "gpus_low", "default"],
                        label="Cola de Prioridad",
                        value="gpus_high"
                    )
                description = gr.Textbox(label="Descripción del experimento", lines=2)
            
            launch_btn = gr.Button("🚀 ENVIAR AL CLUSTER", variant="primary", size="lg")
            output_msg = gr.Textbox(label="Estado del Sistema", lines=4, interactive=False)

    # Event Handlers
    is_demo.change(
        fn=handle_mode_change,
        inputs=[is_demo],
        outputs=[task_type, data_path]
    )
    
    # Pre-load demo logic
    task_type.change(
        fn=handle_task_change,
        inputs=[task_type, is_demo],
        outputs=[model, data_path, epochs, imgsz, author, description]
    )
    
    # Initialize UI
    demo.load(
        fn=handle_task_change,
        inputs=[task_type, is_demo],
        outputs=[model, data_path, epochs, imgsz, author, description]
    )

    launch_btn.click(
        fn=launch_training,
        inputs=[task_type, is_demo, model, data_path, epochs, imgsz, author, description, queue],
        outputs=[output_msg]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
