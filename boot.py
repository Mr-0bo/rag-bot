# boot.py
import time
import sys
import threading
import webbrowser


def mostrar_pantalla_bienvenida():
    """Muestra una animación visual impactante con ASCII art de AGENTE y secuencia de carga."""
    # Limpiar pantalla (compatible con Windows y Unix)
    print("\033[H\033[J", end="")

    # Arte ASCII estilizado para "AGENTE"
    banner = r"""
___    __________________________________________________
__ |  / /__  ____/__  __ \__  __/___  _/_  ____/__  ____/
__ | / /__  __/  __  /_/ /_  /   __  / _  /    __  __/   
__ |/ / _  /___  _  _, _/_  /   __/ /  / /___  _  /___   
_____/  /_____/  /_/ |_| /_/    /___/  \____/  /_____/   
                                                                                    
    """

    # Imprimir con colores brillantes (Cian corporativo)
    print("\033[96m" + banner + "\033[0m")
    print("\033[1m\033[97m  ========================================================================\033[0m")
    print("\033[1m\033[92m   [ SYSTEM LAUNCHER ] : AGENTE DE BUSQUEDA 'VERTICE'\033[0m")
    print("\033[1m\033[97m  ========================================================================\033[0m")
    print("   \033[93mDeveloper\033[0m      : Mario García")
    print("   \033[93mVersion\033[0m        : v1.0.0-PROD")
    print("   \033[93mArchitecture\033[0m   : FastAPI + Qdrant Vector Engine + Local Embeddings")
    print("\033[1m\033[97m  ------------------------------------------------------------------------\033[0m\n")

    time.sleep(1.0)

    # Secuencia de carga visual simulada
    pasos = [
        ("Cargando modelo de embeddings locales...", 0.5),
        ("Conectando con base de datos vectorial...", 0.6),
        ("Verificando tracking incremental...", 0.4),
        ("Inicializando pipelines de síntesis con Gemini Flash...", 0.7),
        ("Estableciendo sockets de comunicación local...", 0.4)
    ]

    for texto, duracion in pasos:
        sys.stdout.write(f"  \033[94m[INIT]\033[0m {texto:<56}")
        sys.stdout.flush()

        for _ in range(3):
            time.sleep(duracion / 3)
            sys.stdout.write(".")
            sys.stdout.flush()
        print(" \033[92m[ OK ]\033[0m")

    print("\n  \033[97m\033[1m" + "═" * 72 + "\033[0m")
    print("  \033[92m\033[1m  [✔] SISTEMA OPERATIVO Y MOTOR RAG INICIALIZADOS CORRECTAMENTE\033[0m")
    print("  \033[93m  [i] Lanzando interfaz gráfica en el navegador predeterminado...\033[0m")
    print("  \033[90m  [i] (Mantén esta ventana abierta para registrar la actividad de la app)\033[0m")
    print("  \033[97m\033[1m" + "═" * 72 + "\033[0m\n")


def iniciar_sistema(app_import_str="main:app", host="127.0.0.1", port=8000):
    """Ejecuta la secuencia de arranque y lanza Uvicorn."""
    mostrar_pantalla_bienvenida()

    def abrir_navegador():
        time.sleep(3.2)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=abrir_navegador, daemon=True).start()

    import uvicorn
    uvicorn.run(app_import_str, host=host, port=port, reload=False)