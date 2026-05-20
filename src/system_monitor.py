"""
Monitora CPU/GPU e avisa o gremlin quando passar do limite.
"""

import subprocess
import threading
import time


class SystemMonitor:

    def __init__(self, cpu_threshold=70.0, gpu_threshold=80.0):
        self.cpu_threshold = cpu_threshold
        self.gpu_threshold = gpu_threshold
        self.on_stress = None       # callback: chamado quando CPU ou GPU passa do limite
        self.running = False
        self._thread = None
        self._last_reaction = 0    # evita spam de reações
        self.on_fullscreen = None      # callback: chamado quando fullscreen muda
        self.on_music = None           # callback: chamado quando música começa/para
        self._is_music = False
        self._is_fullscreen = False    # estado atual
        self._last_fullscreen_check = 0

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
    def _loop(self):
        while self.running:
            try:
                cpu = self._get_cpu()
                gpu = self._get_gpu()

                now = time.time()
                cooldown_ok = (now - self._last_reaction) > 10
                if cooldown_ok and (cpu > self.cpu_threshold or gpu > self.gpu_threshold):
                    self._last_reaction = now
                    if self.on_stress:
                        self.on_stress(cpu, gpu)

                music = self._get_music()
                if music != self._is_music:
                    self._is_music = music
                    if self.on_music:
                        self.on_music(music)

                fullscreen = self._get_fullscreen()
                if fullscreen != self._is_fullscreen:
                    self._is_fullscreen = fullscreen
                    if self.on_fullscreen:
                        self.on_fullscreen(fullscreen)

            except Exception as e:
                print(f"[SystemMonitor] Erro: {e}")

            time.sleep(2)

    def _get_cpu(self) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            result = subprocess.run(
                "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'",
                shell=True, capture_output=True, text=True, timeout=1
            )
            return float(result.stdout.strip()) if result.stdout else 0.0

    def _get_gpu(self) -> float:
        try:
            result = subprocess.run(
                "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits",
                shell=True, capture_output=True, text=True, timeout=1
            )
            return float(result.stdout.strip()) if result.stdout else 0.0
        except:
            return 0.0

    def _get_fullscreen(self) -> bool:
        """Detecta se um jogo esta rodando via processos Steam/Lutris/Wine."""
        try:
            import psutil
            gaming_processes = [
                'gameoverlayui', 'GameOverlayUI',  # Steam overlay = jogo rodando
                'lutris', 'wine', 'wineserver',
                'gamemode', 'gamemoderun',
            ]
            for proc in psutil.process_iter(["name"]):
                try:
                    if proc.info["name"] in gaming_processes:
                        return True
                except:
                    pass
        except:
            pass
        return False

    def _get_music(self) -> bool:
        """Detecta se ha audio sendo reproduzido via PipeWire."""
        try:
            result = subprocess.run(
                'pw-dump',
                shell=True, capture_output=True, text=True, timeout=2
            )
            import json
            data = json.loads(result.stdout)
            for obj in data:
                props = obj.get('info', {}).get('props', {})
                state = obj.get('info', {}).get('state', '')
                app = props.get('application.name', '')
                # ignora o proprio gremlin
                if state == 'running' and 'python' not in app.lower() and app:
                    return True
        except:
            pass
        return False
