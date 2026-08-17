# Plugins AD5X - read-only bridge from Z-Mod IFS state to Klipper status API.
#
# Z-Mod remains the sole owner of the IFS serial protocol.  This adapter only
# snapshots the in-memory IfsData already maintained by zmod_ifs, allowing
# Moonraker clients to subscribe through the standard printer.objects API.

FFS_STATE_NAMES = {
    3: "polling",
    5: "ready",
    7: "clamped",
    11: "loading",
    12: "releasing",
    15: "unloading",
    127: "driver_error",
}


class AD5XIFS:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.zmod_ifs = None
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:disconnect", self._handle_disconnect)
        self.printer.register_event_handler("klippy:shutdown", self._handle_disconnect)

    def _handle_ready(self):
        candidate = self.printer.lookup_object("zmod_ifs", None)
        if candidate is None or not hasattr(candidate, "ifs_data"):
            self.zmod_ifs = None
            return
        self.zmod_ifs = candidate

    def _handle_disconnect(self):
        self.zmod_ifs = None

    def _unavailable(self):
        return {
            "available": False,
            "state": "unavailable",
            "state_code": 0,
            "active_slot": 0,
            "slots": [],
            "silk_mask": 0,
            "raw_channel": 0,
            "insert_slot": 0,
            "need_insert": False,
            "stall": False,
            "stall_mask": 0,
        }

    def get_status(self, eventtime):
        zmod_ifs = self.zmod_ifs
        if zmod_ifs is None:
            return self._unavailable()

        ifs_data = getattr(zmod_ifs, "ifs_data", None)
        if ifs_data is None or not hasattr(ifs_data, "get_values"):
            return self._unavailable()

        values = ifs_data.get_values()
        ports = list(values.get("Ports") or [])
        state_code = int(values.get("State") or 0)
        silk_mask = int(values.get("Silk") or 0)
        raw_channel = int(values.get("Chan") or 0)
        insert_slot = int(values.get("Insert") or 0)
        stall_mask = int(values.get("stall_state") or 0)

        # cur_port is the Z-Mod runtime selection populated from FFMInfo.channel.
        # It is intentionally distinct from the raw F13 `chan` diagnostic field.
        active_slot = int(getattr(ifs_data, "cur_port", 0) or 0)
        if active_slot < 0 or active_slot > len(ports):
            active_slot = 0

        slots = []
        for index, present in enumerate(ports, start=1):
            slots.append({
                "slot": index,
                "present": bool(present),
                "stall": bool(stall_mask & (1 << (index - 1))),
            })

        available = bool(getattr(zmod_ifs, "get_ifs_status", lambda: True)())
        return {
            "available": available,
            "state": FFS_STATE_NAMES.get(state_code, "unknown"),
            "state_code": state_code,
            "active_slot": active_slot,
            "slots": slots,
            "silk_mask": silk_mask,
            "raw_channel": raw_channel,
            "insert_slot": insert_slot,
            "need_insert": bool(values.get("NeedInsert", False)),
            "stall": bool(values.get("Stall", False)),
            "stall_mask": stall_mask,
        }


def load_config(config):
    return AD5XIFS(config)
