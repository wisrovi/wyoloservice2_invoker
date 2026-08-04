import yaml
import json
from celery_client import _get_hm, _HASH_KEY

# ── Quick templates (internal constants) ────────────────────────────

_TEMPLATE_CLS: str = """model: "yolov8n-cls.pt"
type: "yolo"
train:
  data: "/examples/colorball.v8i.multiclass/"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "color_ball_v2"
  tune: true
  sampler: "TPESampler"
  n_trials: 1
  search_space:
    model: [ "choice", "yolov8n-cls.pt" ]
    train:
      imgsz: [ "choice", 416 ]
      lr0: [ "loguniform", 1e-5, 1e-2 ]
extras:
  gpu:
    id: 0
    limit: 0.95
metadata:
  content: "Este es un experimento de clasificación de imágenes."
  author: "William Rodriguez"
  documentation: "Este modelo fue entrenado con datos del 2025."
"""

_TEMPLATE_DET: str = """model: "yolov8n.pt"
type: "yolo"
train:
  batch: -1
  data: "/examples/Deteksi_komponen_elektronik.v1i/data.yaml"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "elektronik_v2"
  tune: true
  sampler: "TPESampler"
  n_trials: 1
  search_space:
    model: [ "choice", "yolov8n.pt" ]
    train:
      imgsz: [ "choice", 416 ]
      lr0: [ "loguniform", 1e-5, 1e-2 ]
extras:
  gpu:
    id: 0
    limit: 0.95
metadata:
  content: "Este es un experimento de clasificación de imágenes."
  author: "William Rodriguez"
  documentation: "Este modelo fue entrenado con datos del 2025."
"""

_TEMPLATE_SEG: str = """model: "yolov8n-seg.pt"
type: "yolo"
# dvc_data_path: /datasets/clasificacion/colorball.v8i.multiclass.dvc
train:
  data: "/examples/ArchitecturePlan/data.yaml"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "ArchitecturePlan"
  sampler: "TPESampler"
  fitness: "metrics/mAP50(M)"
  n_trials: 1
  search_space:
    #model: ["choice", "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt"]
    train:
      imgsz: ["choice", 640]
      lr0: ["loguniform", 1e-5, 1e-2]
      momentum: ["range", 0.85, 0.98, 0.01]
      freeze: ["range", 1, 5, 1]
      optimizer: ["choice", SGD, Adam, AdamW, NAdam, RMSProp]
extras:
  gpu:
    id: 0
    limit: 0.60
metadata:
  content: "Este es un entrenamiento de prueba de Wisrovi"
  author: "Manu G"
  documentation: "Este modelo fue entrenado con datos de marzo 2025."
"""

def get_template_from_redis(template_type: str, default_content: str) -> str:
    """Fetch template from central Redis, or initialize it with default if it doesn't exist."""
    hm = _get_hm()
    if hm is None:
        return default_content
    try:
        raw = hm.read_hash(hash_name="invoker:shared_templates", key=template_type)
        if raw is None or not str(raw).strip():
            hm.create_hash(hash_name="invoker:shared_templates", key=template_type, value=default_content)
            return default_content
        return str(raw)
    except Exception:
        return default_content

def load_template() -> str:
    """Load the last saved template from the Redis hash. Returns default classification on fallback."""
    hm = _get_hm()
    if hm is None:
        return get_template_from_redis("classification", _TEMPLATE_CLS)
    try:
        raw = hm.read_hash(hash_name=_HASH_KEY, key="template")
        if raw is None:
            return get_template_from_redis("classification", _TEMPLATE_CLS)

        # dict format
        if isinstance(raw, dict):
            if raw:
                return yaml.dump(raw, default_flow_style=False, allow_unicode=True)
            return get_template_from_redis("classification", _TEMPLATE_CLS)

        # string format
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
            except json.JSONDecodeError:
                pass
            return raw

        return get_template_from_redis("classification", _TEMPLATE_CLS)
    except Exception:
        return get_template_from_redis("classification", _TEMPLATE_CLS)
