"""
feature_config.py
Definición centralizada de las features del modelo de similitud.
Todas las features provienen de datos WhoScored (eventos de partido).
Son métricas per-90 minutos o ratios (adimensionales).
"""

# Columnas identificadoras (no entran al modelo)
ID_COLUMNS = ["player_id", "player_name", "team", "league", "position", "minutes", "matches"]

# --- Features de volumen (per 90) ---
# Qué tanto hace el jugador
VOLUME_FEATURES = [
    "goals_p90",
    "shots_total_p90",
    "shots_on_target_p90",
    "key_passes_p90",
    "assists_p90",
    "passes_total_p90",
    "passes_progressive_p90",
    "passes_into_box_p90",
    "crosses_p90",
    "throughballs_p90",
    "dribbles_won_p90",
    "touches_p90",
    "carries_p90",
    "tackles_p90",
    "interceptions_p90",
    "ball_recoveries_p90",
    "aerials_won_p90",
]

# --- Features de estilo (ratios, adimensionales) ---
# Cómo lo hace: perfil técnico independiente del volumen de juego
STYLE_FEATURES = [
    "shot_accuracy_pct",        # tiros a puerta / tiros totales
    "shots_from_box_pct",       # tiros desde área / tiros totales
    "pass_completion_pct",      # pases completados / pases totales
    "passes_forward_pct",       # pases hacia adelante / pases totales
    "passes_progressive_pct",   # pases progresivos / pases totales
    "passes_into_box_pct",      # pases al área / pases totales
    "passes_switch_pct",        # cambios de juego / pases totales
    "avg_pass_length",          # longitud media de pase (metros)
    "dribble_success_pct",      # regates exitosos / regates intentados
    "aerial_win_pct",           # duelos aéreos ganados / totales
    "defensive_actions_p90",    # tackles + intercepciones + recuperaciones per 90
    "carry_distance_p90",       # distancia conducción per 90
]

MODEL_FEATURES = VOLUME_FEATURES + STYLE_FEATURES
