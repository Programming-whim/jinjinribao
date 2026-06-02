"""Web 版定时器：后台线程轮询，不依赖 tkinter"""

import threading
import datetime


class WebScheduler:
    def __init__(self, time_getter, enabled_getter, trigger_callback):
        self._get_time = time_getter
        self._get_enabled = enabled_getter
        self._trigger = trigger_callback
        self._last_run_date = None
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def reload(self):
        """配置变更后调用，下次轮询时自动读取最新值"""
        pass

    def _run(self):
        while not self._stop_event.is_set():
            try:
                if self._get_enabled():
                    now = datetime.datetime.now()
                    target = self._get_time()  # "HH:MM"
                    current_hm = now.strftime("%H:%M")

                    if current_hm == target and self._last_run_date != now.date():
                        self._last_run_date = now.date()
                        self._trigger()
            except Exception:
                pass
            self._stop_event.wait(30)
