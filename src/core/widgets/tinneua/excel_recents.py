import json
import logging
import os
import re
import subprocess
import webbrowser
import winreg
from datetime import datetime
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from core.config import HOME_CONFIGURATION_DIR
from core.utils.utilities import PopupWidget, add_shadow, build_widget_label, is_valid_qobject
from core.utils.widgets.animation_manager import AnimationManager
from core.validation.widgets.tinneua.excel_recents import ExcelRecentsConfig
from core.widgets.base import BaseWidget


class ExcelRecentsWidget(BaseWidget):
    validation_schema = ExcelRecentsConfig

    _OFFICE_VERSIONS = ("16.0", "15.0", "14.0", "12.0")
    _SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".xltx", ".xltm", ".xlam", ".csv")
    _MRU_ENTRY_PATTERN = re.compile(
        r"^\[F(?P<flags>[0-9A-Fa-f]{8})\]\[T(?P<timestamp>[0-9A-Fa-f]{16})\](?:\[O(?P<open_count>[0-9A-Fa-f]{8})\])?(?P<path>.*)$"
    )

    def __init__(self, config: ExcelRecentsConfig):
        super().__init__(
            timer_interval=config.update_interval if config.update_interval > 0 else None,
            class_name=f"excel-recents-widget {config.class_name}",
        )
        self.config = config
        self._show_alt_label = False
        self._menu: PopupWidget | None = None
        self._favorites_path = self._resolve_favorites_path()
        self._favorites: set[str] = self._load_favorites()
        self._cached_items: list[dict] = []

        self._widget_container_layout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(
            self.config.container_padding.left,
            self.config.container_padding.top,
            self.config.container_padding.right,
            self.config.container_padding.bottom,
        )

        self._widget_container = QFrame()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        add_shadow(self._widget_container, self.config.container_shadow.model_dump())
        self.widget_layout.addWidget(self._widget_container)

        build_widget_label(
            self,
            self.config.label,
            self.config.label_alt,
            self.config.label_shadow.model_dump(),
        )

        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("toggle_menu", self._toggle_menu)
        self.register_callback("update_label", self._update_label)
        self.register_callback("refresh_data", self._refresh_data)

        self.callback_left = self.config.callbacks.on_left
        self.callback_right = self.config.callbacks.on_right
        self.callback_middle = self.config.callbacks.on_middle
        self.callback_timer = "refresh_data"

        self._refresh_data()
        if self.timer_interval:
            self.start_timer()

    def _resolve_favorites_path(self) -> str:
        if self.config.favorites_path and self.config.favorites_path.strip():
            return os.path.expanduser(self.config.favorites_path)
        return os.path.join(HOME_CONFIGURATION_DIR, "excel_recents_favorites.json")

    def _refresh_data(self):
        self._cached_items = self._get_recent_items()
        self._update_label()

    def _toggle_label(self):
        if self.config.animation.enabled:
            AnimationManager.animate(self, self.config.animation.type, self.config.animation.duration)

        self._show_alt_label = not self._show_alt_label
        for widget in self._widgets:
            widget.setVisible(not self._show_alt_label)
        for widget in getattr(self, "_widgets_alt", []):
            widget.setVisible(self._show_alt_label)
        self._update_label()

    def _toggle_menu(self):
        if self.config.animation.enabled:
            AnimationManager.animate(self, self.config.animation.type, self.config.animation.duration)

        if self._menu and is_valid_qobject(self._menu) and self._menu.isVisible():
            self._close_menu()
            return

        self._refresh_data()
        self._show_menu()

    def _show_menu(self):
        self._menu = PopupWidget(
            self,
            self.config.menu.blur,
            self.config.menu.round_corners,
            self.config.menu.round_corners_type,
            self.config.menu.border_color,
        )
        self._menu.setProperty("class", "excel-recents-menu")

        main_layout = QVBoxLayout(self._menu)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setProperty("class", "scroll-area")
        scroll_area.setViewportMargins(0, 0, -4, 0)
        scroll_area.setStyleSheet("""
            QScrollBar:vertical { border: none; background:transparent; width: 4px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.2); min-height: 10px; border-radius: 2px; }
            QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.35); }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical { height: 0px; }
        """)
        main_layout.addWidget(scroll_area)

        scroll_widget = QWidget()
        scroll_widget.setProperty("class", "contents")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        scroll_area.setWidget(scroll_widget)

        if not self._cached_items:
            empty_label = QLabel("No recent Excel files found.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setContentsMargins(0, 12, 0, 12)
            empty_label.setProperty("class", "empty-list")
            scroll_layout.addWidget(empty_label)
        else:
            for item in self._cached_items:
                scroll_layout.addWidget(self._create_item_widget(item))

        self._menu.adjustSize()
        self._menu.setPosition(
            alignment=self.config.menu.alignment,
            direction=self.config.menu.direction,
            offset_left=self.config.menu.offset_left,
            offset_top=self.config.menu.offset_top,
        )
        self._menu.show()

    def _close_menu(self):
        if not self._menu:
            return
        try:
            if is_valid_qobject(self._menu):
                self._menu.hide_animated()
        except RuntimeError:
            pass
        finally:
            self._menu = None

    def _create_item_widget(self, item: dict) -> QWidget:
        container = QWidget()
        container.setProperty("class", "item")
        container.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        icon_label = QLabel(self.config.icons.file)
        icon_label.setProperty("class", "file-icon")
        layout.addWidget(icon_label)

        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title_label = QLabel(self._truncate_text(item["display_name"], self.config.max_title_length))
        title_label.setProperty("class", "title")
        text_layout.addWidget(title_label)

        path_label = QLabel(self._truncate_text(item["location"], self.config.max_path_length))
        path_label.setProperty("class", "path")
        text_layout.addWidget(path_label)

        layout.addWidget(text_container, 1)

        if item["excel_pinned"]:
            marker = self.config.icons.pinned
        elif item["custom_favorite"]:
            marker = self.config.icons.favorite_on
        else:
            marker = self.config.icons.favorite_off

        favorite_label = QLabel(marker)
        favorite_label.setProperty("class", "favorite-icon")
        layout.addWidget(favorite_label)

        def handle_click(event):
            button = event.button()
            path = item["path"]
            if button == Qt.MouseButton.LeftButton:
                self._open_item(path)
            elif button == Qt.MouseButton.MiddleButton:
                self._toggle_favorite(path)
            elif button == Qt.MouseButton.RightButton:
                self._open_containing_folder(path)

        container.mousePressEvent = handle_click  # type: ignore[assignment]
        return container

    def _toggle_favorite(self, path: str):
        normalized = self._normalize_path(path)
        if not normalized:
            return

        favorite_key = self._favorite_key(normalized)
        favorites = self._load_favorites()
        if favorite_key in favorites:
            favorites.remove(favorite_key)
        else:
            favorites.add(favorite_key)

        self._favorites = favorites
        self._save_favorites()
        self._refresh_data()

        if self._menu and is_valid_qobject(self._menu) and self._menu.isVisible():
            self._close_menu()
            self._show_menu()

    def _open_item(self, path: str):
        try:
            parsed = urlparse(path)
            if parsed.scheme in ("http", "https"):
                webbrowser.open(path)
            else:
                os.startfile(path)
        except Exception:
            try:
                subprocess.Popen(["explorer.exe", path])
            except Exception as e:
                logging.error(f"Failed to open Excel item '{path}': {e}")
        self._close_menu()

    def _open_containing_folder(self, path: str):
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            base = path.rsplit("/", 1)[0] if "/" in path else path
            webbrowser.open(base)
            return

        target = path if os.path.isdir(path) else os.path.dirname(path)
        if not target:
            return

        try:
            subprocess.Popen(["explorer.exe", target])
        except Exception as e:
            logging.error(f"Failed to open folder for '{path}': {e}")

    def _update_label(self):
        items = self._cached_items
        active_widgets = self._widgets_alt if self._show_alt_label and hasattr(self, "_widgets_alt") else self._widgets
        active_label = self.config.label_alt if self._show_alt_label else self.config.label

        label_parts = [part for part in re.split(r"(<span.*?>.*?</span>)", active_label) if part]
        widget_index = 0

        for part in label_parts:
            if widget_index >= len(active_widgets):
                break

            part = part.strip()
            current_widget = active_widgets[widget_index]
            if "<span" in part and "</span>" in part:
                icon = re.sub(r"<span.*?>|</span>", "", part).strip()
                current_widget.setText(icon)
            else:
                try:
                    current_widget.setText(part.format(count=len(items)))
                except Exception:
                    current_widget.setText(part)
            widget_index += 1

    def _get_recent_items(self) -> list[dict]:
        self._favorites = self._load_favorites()
        entries_by_key: dict[str, dict] = {}

        for entry in self._read_excel_mru_entries():
            path = entry.get("path")
            if not path or not self._is_supported(path):
                continue

            entry_key = self._favorite_key(path)
            existing = entries_by_key.get(entry_key)
            if existing:
                existing["excel_pinned"] = existing["excel_pinned"] or entry["excel_pinned"]
                existing["order"] = min(existing["order"], entry["order"])
                existing["timestamp"] = self._most_recent(existing.get("timestamp"), entry.get("timestamp"))
            else:
                entries_by_key[entry_key] = entry

        items: list[dict] = []
        for entry in entries_by_key.values():
            path = entry["path"]
            if self.config.hide_missing_files and not self._path_exists(path):
                continue

            custom_favorite = self._favorite_key(path) in self._favorites
            is_favorite = bool(entry["excel_pinned"] or custom_favorite)
            items.append(
                {
                    **entry,
                    "custom_favorite": custom_favorite,
                    "is_favorite": is_favorite,
                    "display_name": self._display_name_from_path(path),
                    "location": self._location_from_path(path),
                }
            )

        items.sort(
            key=lambda item: (
                0 if item["excel_pinned"] else (1 if item["is_favorite"] else 2),
                item["order"],
                -self._timestamp_sort_value(item.get("timestamp")),
                item["path"].lower(),
            )
        )
        return items[: self.config.max_items]

    def _read_excel_mru_entries(self) -> list[dict]:
        results: list[dict] = []

        for version in self._OFFICE_VERSIONS:
            user_mru_base = rf"Software\Microsoft\Office\{version}\Excel\User MRU"
            global_mru_path = rf"Software\Microsoft\Office\{version}\Excel\File MRU"

            results.extend(self._read_user_mru(user_mru_base))
            results.extend(self._read_entries_from_key(global_mru_path))

        return results

    def _read_user_mru(self, user_mru_base: str) -> list[dict]:
        results: list[dict] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_mru_base) as base_key:
                subkey_count, _, _ = winreg.QueryInfoKey(base_key)
                for idx in range(subkey_count):
                    subkey_name = winreg.EnumKey(base_key, idx)
                    path = rf"{user_mru_base}\{subkey_name}\File MRU"
                    results.extend(self._read_entries_from_key(path))
        except FileNotFoundError:
            return []
        except Exception as e:
            logging.error(f"Failed reading Excel user MRU from '{user_mru_base}': {e}")
        return results

    def _read_entries_from_key(self, key_path: str) -> list[dict]:
        entries: list[dict] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                _, value_count, _ = winreg.QueryInfoKey(key)
                for i in range(value_count):
                    name, value, _ = winreg.EnumValue(key, i)
                    if not name.lower().startswith("item"):
                        continue
                    parsed = self._parse_mru_value(value)
                    if not parsed:
                        continue
                    parsed["order"] = self._extract_item_order(name)
                    entries.append(parsed)
        except FileNotFoundError:
            return []
        except Exception as e:
            logging.error(f"Failed reading Excel MRU entries from '{key_path}': {e}")
        return entries

    def _parse_mru_value(self, value) -> dict | None:
        try:
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-16le")
                except Exception:
                    value = value.decode(errors="ignore")
            text = str(value).strip()
        except Exception:
            return None

        if not text:
            return None

        match = self._MRU_ENTRY_PATTERN.match(text)
        if match:
            flags_hex = match.group("flags")
            timestamp_hex = match.group("timestamp")
            raw_open_count = match.group("open_count")
            raw_path = match.group("path")
            normalized_path = self._normalize_path(raw_path)
            if not normalized_path:
                return None
            return {
                "path": normalized_path,
                "excel_pinned": bool(int(flags_hex, 16) & 1),
                "open_count": int(raw_open_count, 16) if raw_open_count else 0,
                "timestamp": self._filetime_to_datetime(int(timestamp_hex, 16)),
                "order": 0,
            }

        fallback_path = self._extract_path_fallback(text)
        normalized_path = self._normalize_path(fallback_path)
        if not normalized_path:
            return None
        return {
            "path": normalized_path,
            "excel_pinned": False,
            "open_count": 0,
            "timestamp": None,
            "order": 0,
        }

    def _extract_path_fallback(self, value: str) -> str | None:
        candidate = value.strip()
        if "]" in candidate:
            candidate = candidate.rsplit("]", 1)[-1].strip()

        if "," in candidate and re.match(r"^\d+,", candidate):
            candidate = candidate.split(",", 1)[1].strip()

        candidate = candidate.lstrip("*").strip().strip('"')
        if not candidate:
            return None

        return candidate

    def _normalize_path(self, path: str | None) -> str:
        if not path:
            return ""

        cleaned = path.strip().strip('"').lstrip("*").strip()
        if not cleaned:
            return ""

        parsed = urlparse(cleaned)
        if parsed.scheme in ("http", "https"):
            return cleaned

        if parsed.scheme == "file":
            file_path = unquote(parsed.path or "")
            if parsed.netloc:
                file_path = f"\\\\{parsed.netloc}{file_path}"
            file_path = file_path.replace("/", "\\")
            if re.match(r"^\\[A-Za-z]:\\", file_path):
                file_path = file_path[1:]
            return os.path.normpath(file_path)

        if cleaned.lower().startswith("file:///"):
            converted = unquote(cleaned[8:]).replace("/", "\\")
            if re.match(r"^[A-Za-z]:\\", converted):
                return os.path.normpath(converted)

        if "\\" in cleaned or re.match(r"^[A-Za-z]:/", cleaned):
            return os.path.normpath(cleaned.replace("/", "\\"))

        return cleaned

    def _favorite_key(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            return path.rstrip("/").lower()
        return os.path.normcase(path)

    def _filetime_to_datetime(self, filetime: int) -> datetime | None:
        try:
            return datetime.fromtimestamp(filetime / 10**7 - 11644473600)
        except Exception:
            return None

    def _extract_item_order(self, item_name: str) -> int:
        match = re.search(r"(\d+)", item_name)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except ValueError:
            return 0

    def _is_supported(self, path: str) -> bool:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            return True
        return path.lower().endswith(self._SUPPORTED_EXTENSIONS)

    def _path_exists(self, path: str) -> bool:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            return True
        return os.path.exists(path)

    def _display_name_from_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            from_url = os.path.basename(parsed.path.rstrip("/"))
            return from_url or path
        return os.path.basename(path) or path

    def _location_from_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            return path.rsplit("/", 1)[0] if "/" in path else path
        return os.path.dirname(path) or path

    def _truncate_text(self, text: str, max_length: int) -> str:
        if max_length and len(text) > max_length:
            return text[: max_length - 3] + "..."
        return text

    def _timestamp_sort_value(self, timestamp: datetime | None) -> float:
        if not timestamp:
            return 0.0
        try:
            return timestamp.timestamp()
        except Exception:
            return 0.0

    def _most_recent(self, left: datetime | None, right: datetime | None) -> datetime | None:
        if left and right:
            return left if left > right else right
        return left or right

    def _load_favorites(self) -> set[str]:
        try:
            if os.path.exists(self._favorites_path):
                with open(self._favorites_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if isinstance(data, list):
                        normalized = set()
                        for item in data:
                            raw = str(item).strip()
                            if not raw:
                                continue
                            value = self._normalize_path(raw) or raw
                            normalized.add(self._favorite_key(value))
                        return normalized
        except Exception as e:
            logging.error(f"Failed to load Excel favorites from '{self._favorites_path}': {e}")
        return set()

    def _save_favorites(self):
        try:
            parent = os.path.dirname(self._favorites_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self._favorites_path, "w", encoding="utf-8") as handle:
                json.dump(sorted(self._favorites), handle, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save Excel favorites to '{self._favorites_path}': {e}")
