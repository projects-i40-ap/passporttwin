"""
Configuración común de la suite.

Los tests nunca deben depender de la red ni del estado de `.env`: se fuerza el
modo determinista y se desactiva la sonda de `llama.cpp`, de modo que la suite
dé el mismo resultado con el servidor de inferencia encendido o apagado.

Los tests que necesitan ejercitar la rama LLM construyen el extractor con
`enabled=True` o parchean `llama_cpp_available`, así que siguen cubriéndola.
"""

import os

os.environ["AI_LEGO_ENABLED"] = "false"
os.environ["AI_PROBE_ENABLED"] = "false"
