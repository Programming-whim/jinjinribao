"""应用内定时器：基于 tkinter .after() 轮询，不阻塞主线程"""

import datetime
from app.constants import SCHEDULE_POLL_INTERVAL_MS


class ReportScheduler:
    def __init__(self, time_str_getter, enabled_getter, trigger_callback, tk_root):
        self._get_time = time_str_getter
        self._get_enabled = enabled_getter
        self._trigger = trigger_callback
        self._root = tk_root
        self._last_run_date = None
        self._after_id = None

    def start(self):
        self._poll()

    def stop(self):
        if self._after_id:
            self._root.after_cancel(self._after_id)
            self._after_id = None

    def _poll(self):
        try:
            if self._get_enabled():
                now = datetime.datetime.now()
                target = self._get_time()  # "HH:MM"
                current_hm = now.strftime("%H:%M")

                if current_hm == target and self._last_run_date != now.date():
                    self._last_run_date = now.date()
                    self._trigger()
        except Exception:
            pass  # 定时器异常不应崩溃 GUI

        self._after_id = self._root.after(SCHEDULE_POLL_INTERVAL_MS, self._poll)
