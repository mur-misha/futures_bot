import json
import os
import time
from dataclasses import asdict
from models import AlertKey, Direction, SignalStrength


class StateStore:
    def __init__(self, path: str):
        self.path = path
        self.processed: dict[str, int] = {}
        self.last_alert: dict[str, dict] = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.processed = {k: int(v) for k, v in data.get("processed", {}).items()}
            self.last_alert = data.get("last_alert", {})
        except (OSError, ValueError, TypeError):
            self.processed = {}
            self.last_alert = {}

    def save(self):
        tmp = self.path + ".tmp"
        data = {"processed": self.processed, "last_alert": self.last_alert}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def already_processed(self, symbol: str, candle_time: int) -> bool:
        return self.processed.get(symbol) == candle_time

    def mark_processed(self, symbol: str, candle_time: int):
        self.processed[symbol] = candle_time

    def should_alert(self, key: AlertKey, cooldown_sec: int) -> bool:
        old = self.last_alert.get(key.symbol)
        now = time.time()
        if old:
            if old.get("candle_time") == key.candle_time and old.get("direction") == key.direction.value:
                return False
            # Кулдаун по времени применяется только если направление НЕ изменилось.
            # Разворот (например, был UP, а теперь пришёл DOWN) - это обычно самая
            # ценная информация, и его не стоит подавлять только потому, что недавно
            # был alert в противоположную сторону.
            if old.get("direction") == key.direction.value and now - float(old.get("sent_at", 0)) < cooldown_sec:
                return False
        return True

    def mark_alert(self, key: AlertKey):
        self.last_alert[key.symbol] = {
            "candle_time": key.candle_time,
            "direction": key.direction.value,
            "strength": key.strength.value,
            "sent_at": time.time(),
        }
