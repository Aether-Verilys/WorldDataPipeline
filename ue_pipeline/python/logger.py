from __future__ import annotations

import inspect
import os
from typing import Any, Optional


class Logger:
    @staticmethod
    def _snake_to_camel(name: str) -> str:
        parts = [p for p in name.replace("-", "_").split("_") if p]
        if not parts:
            return name or "Log"
        return "".join(p[:1].upper() + p[1:] for p in parts)

    def _resolve_tag(self, *, stacklevel: int) -> str:
        frame = inspect.currentframe()
        for _ in range(stacklevel):
            if frame is None:
                break
            frame = frame.f_back

        while frame is not None:
            locals_dict = frame.f_locals

            if "self" in locals_dict:
                try:
                    return locals_dict["self"].__class__.__name__
                except Exception:
                    pass

            if "cls" in locals_dict:
                try:
                    candidate = locals_dict["cls"]
                    if isinstance(candidate, type):
                        return candidate.__name__
                except Exception:
                    pass

            file_path = frame.f_globals.get("__file__") or frame.f_code.co_filename
            if file_path:
                base = os.path.splitext(os.path.basename(file_path))[0]
                if base and base != os.path.splitext(os.path.basename(__file__))[0]:
                    return self._snake_to_camel(base)

            module_name = frame.f_globals.get("__name__")
            if module_name and module_name not in ("__main__", "builtins"):
                base = module_name.rsplit(".", 1)[-1]
                return self._snake_to_camel(base)

            frame = frame.f_back

        return "Log"

    def _emit(
        self,
        message: str,
        *,
        level: Optional[str] = None,
        tag: Optional[str] = None,
        stacklevel: int = 3,
    ) -> None:
        resolved_tag = tag or self._resolve_tag(stacklevel=stacklevel)
        if level:
            print(f"[{resolved_tag}] {level}: {message}")
        else:
            print(f"[{resolved_tag}] {message}")

    def info(self, message: str, *, tag: Optional[str] = None) -> None:
        self._emit(message, level=None, tag=tag, stacklevel=3)

    def warning(self, message: str, *, tag: Optional[str] = None) -> None:
        self._emit(message, level="WARNING", tag=tag, stacklevel=3)

    def error(self, message: str, *, tag: Optional[str] = None) -> None:
        self._emit(message, level="ERROR", tag=tag, stacklevel=3)

    def blank(self, lines: int = 1) -> None:
        for _ in range(max(0, int(lines))):
            print("")

    def separator(self, *, width: int = 40, char: str = "-") -> None:
        if not char:
            char = "-"
        self.plain(char[0] * int(width))

    def header(self, title: str, *, width: int = 40, char: str = "=") -> None:
        if not char:
            char = "="
        line = char[0] * int(width)
        self.plain(line)
        self.plain(title)
        self.plain(line)
        self.blank(1)

    def kv(self, key: str, value: Any, *, key_width: int = 14, tag: Optional[str] = None) -> None:
        msg = f"{str(key):{int(key_width)}s} {value}"
        self.info(msg, tag=tag)

    @staticmethod
    def plain(message: str) -> None:
        print(message)


logger = Logger()
