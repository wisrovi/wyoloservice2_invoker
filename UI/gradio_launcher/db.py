import os
from sqlalchemy import create_engine, text

def get_optuna_engine():
    """Initializes and returns SQLAlchemy engine using OPTUNA_DB_URL or default control host."""
    control_host = os.getenv("CONTROL_HOST", "127.0.0.1")
    default_db_url = f"postgresql://postgres:postgres@{control_host}:23436/wyoloservice"
    optuna_db_url = os.getenv("OPTUNA_DB_URL", default_db_url)
    return create_engine(optuna_db_url)

def list_optuna_studies() -> list[str]:
    """Fetch all study names from PostgreSQL database."""
    try:
        engine = get_optuna_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT study_name FROM studies ORDER BY study_id DESC"))
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        print(f"Error listing studies: {e}")
        return []

def get_optuna_study_history(study_name: str) -> str:
    """Fetch history and best trial details for a specific Optuna study."""
    if not study_name or not study_name.strip():
        return "⚠️ *Please select or input a valid study name.*"
        
    study_name = study_name.strip()
    try:
        engine = get_optuna_engine()
        
        # 1. Fetch study details
        with engine.connect() as conn:
            study_row = conn.execute(
                text("""
                SELECT s.study_id, sd.direction 
                FROM studies s
                LEFT JOIN study_directions sd ON s.study_id = sd.study_id
                WHERE s.study_name = :study_name
            """),
                {"study_name": study_name}
            ).fetchone()
            
            if not study_row:
                return f"❌ **Study not found:** '{study_name}'"
                
            study_id, direction = study_row
            
            # 2. Fetch the best trial
            best_row = conn.execute(
                text("""
                SELECT t.trial_id, tv.value, t.datetime_start, t.datetime_complete
                FROM trials t
                JOIN trial_values tv ON t.trial_id = tv.trial_id
                WHERE t.study_id = :study_id AND t.state = 'COMPLETE'
                ORDER BY
                    CASE WHEN :direction = 'MAXIMIZE' THEN tv.value END DESC,
                    CASE WHEN :direction = 'MINIMIZE' THEN tv.value END ASC
                LIMIT 1
            """),
                {"study_id": study_id, "direction": direction}
            ).fetchone()
            
            # 3. Fetch all trials
            trials_rows = conn.execute(
                text("""
                SELECT t.trial_id, t.state, tv.value, t.datetime_start, t.datetime_complete
                FROM trials t
                LEFT JOIN trial_values tv ON t.trial_id = tv.trial_id
                WHERE t.study_id = :study_id
                ORDER BY t.trial_id DESC
            """),
                {"study_id": study_id}
            ).fetchall()

        # Build best trial parameters if found
        best_info_md = ""
        if best_row:
            bt_id, bt_value, bt_start, bt_end = best_row
            # Fetch best trial parameters
            with engine.connect() as conn:
                params_rows = conn.execute(
                    text("SELECT param_name, param_value FROM trial_params WHERE trial_id = :trial_id"),
                    {"trial_id": bt_id}
                ).fetchall()
            params_dict = {p[0]: p[1] for p in params_rows}
            params_formatted = ", ".join([f"`{k}`: **{v}**" for k, v in params_dict.items()])
            
            best_info_md = (
                f"### 🏆 Best Trial Found (Trial #{bt_id})\n"
                f"* **Metric Score:** `{bt_value:.5f}` &nbsp;&nbsp;|&nbsp;&nbsp; **Direction:** `{direction}`\n"
                f"* **Hyperparameters:** {params_formatted}\n"
                f"* **Start:** {bt_start} &nbsp;&nbsp;|&nbsp;&nbsp; **End:** {bt_end}\n\n"
            )
        else:
            best_info_md = "### 🏆 Best Trial Found\n*No completed trials yet in this study.*\n\n"

        # Build trials history table
        table_md = "#### 📋 Trials Log\n\n"
        table_md += "| Trial ID | State | Score | Start Time | Parameters |\n"
        table_md += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        for r in trials_rows:
            t_id, t_state, t_value, t_start, t_end = r
            # Fetch params for this trial
            with engine.connect() as conn:
                params_rows = conn.execute(
                    text("SELECT param_name, param_value FROM trial_params WHERE trial_id = :trial_id"),
                    {"trial_id": t_id}
                ).fetchall()
            t_params_dict = {p[0]: p[1] for p in params_rows}
            t_params_formatted = ", ".join([f"`{k}`: {v}" for k, v in t_params_dict.items()])
            
            val_str = f"{t_value:.5f}" if t_value is not None else "-"
            state_emoji = "🟢" if t_state == "COMPLETE" else ("🟡" if t_state == "RUNNING" else "🔴")
            
            table_md += f"| #{t_id} | {state_emoji} {t_state} | **{val_str}** | {t_start} | {t_params_formatted} |\n"

        return f"{best_info_md}{table_md}"
    except Exception as exc:
        return f"❌ **Optuna Connection Error:** {exc}"
