import json
import logging
import re
from typing import Any, override
from uuid import UUID

import win32gui
from PyQt6.QtCore import QPropertyAnimation, QPoint, QRect, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from win32con import WM_LBUTTONDBLCLK, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP

from core.utils.utilities import PopupWidget, add_shadow, app_data_path, build_widget_label, is_valid_qobject
from core.utils.widgets.animation_manager import AnimationManager
from core.utils.widgets.systray.systray_monitor import IconData, SystrayMonitor
from core.utils.widgets.systray.systray_widget import IconState, IconWidget
from core.utils.win32.bindings import IsWindow
from core.utils.win32.constants import (
    NIF_GUID,
    NIF_ICON,
    NIF_INFO,
    NIF_MESSAGE,
    NIF_STATE,
    NIF_TIP,
)
from core.validation.widgets.tinneua.systray_popup import SystrayPopupConfig
from core.widgets.base import BaseWidget

logger = logging.getLogger("systray_popup_widget")

BATTERY_ICON_GUID = UUID("7820ae75-23e3-4229-82c1-e41cb67d5b9c")
VOLUME_ICON_GUID = UUID("7820ae73-23e3-4229-82c1-e41cb67d5b9c")
NETWORK_GUID = UUID("7820ae74-23e3-4229-82c1-e41cb67d5b9c")


class PersistentPopupWidget(PopupWidget):
    """Popup widget variant that can be hidden without deleting itself."""

    def __init__(
        self,
        parent: QWidget,
        blur: bool = False,
        round_corners: bool = False,
        round_corners_type: str = "normal",
        border_color: str = "None",
        dark_mode: bool = False,
    ):
        super().__init__(
            parent=parent,
            blur=blur,
            round_corners=round_corners,
            round_corners_type=round_corners_type,
            border_color=border_color,
            dark_mode=dark_mode,
        )
        # Use Tool window semantics to avoid implicit Qt.Popup auto-dismiss
        # while keeping explicit outside-click close via PopupWidget event filter.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )

    def _remove_from_registry(self):
        try:
            parent_id = id(self._parent)
            if parent_id in PopupWidget._open_popups and PopupWidget._open_popups[parent_id] is self:
                PopupWidget._open_popups.pop(parent_id, None)
        except Exception:
            pass

    def _on_animation_finished(self):
        if not self._is_closing:
            return

        self._remove_from_registry()
        try:
            QWidget.hide(self)
            self.setWindowOpacity(1.0)
        except Exception:
            pass
        self._is_closing = False

    def hide_animated(self):
        if self._is_closing:
            return
        try:
            if self._fade_animation.state() == QPropertyAnimation.State.Running:
                self._fade_animation.stop()
        except Exception:
            pass

        current_opacity = self.windowOpacity()
        if current_opacity <= 0.0:
            current_opacity = 1.0
            self.setWindowOpacity(1.0)

        self._is_closing = True
        self._fade_animation.setStartValue(current_opacity)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def hide(self):
        try:
            if self._fade_animation.state() == QPropertyAnimation.State.Running:
                self._fade_animation.stop()
        except Exception:
            pass

        self._is_closing = True
        self._remove_from_registry()
        try:
            QWidget.hide(self)
            self.setWindowOpacity(1.0)
        except Exception:
            pass
        self._is_closing = False


class SystrayPopupIconWidget(IconWidget):
    """Systray icon button variant with middle-click pin/unpin and no drag/reorder."""

    action_invoked = pyqtSignal(object)

    @override
    def mousePressEvent(self, e: QMouseEvent | None) -> None:
        if e is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.last_cursor_pos = e.pos()
            self.lmb_pressed = True
            self.update_scaled_pixmap()
        QPushButton.mousePressEvent(self, e)

    @override
    def mouseMoveEvent(self, e: QMouseEvent | None) -> None:
        # Drag/reorder is intentionally disabled for this widget.
        if e is None:
            return
        QPushButton.mouseMoveEvent(self, e)

    @override
    def mouseReleaseEvent(self, e: QMouseEvent | None) -> None:
        if e is None:
            QPushButton.mouseReleaseEvent(self, e)
            return

        if self.ignore_next_release:
            self.ignore_next_release = False
            QPushButton.mouseReleaseEvent(self, e)
            return

        self.lmb_pressed = False
        btn = e.button()
        if btn == Qt.MouseButton.LeftButton and (self.last_cursor_pos - e.pos()).manhattanLength() > 8:
            QPushButton.mouseReleaseEvent(self, e)
            return

        if btn == Qt.MouseButton.LeftButton:
            self.send_action(WM_LBUTTONDOWN)
            self.send_action(WM_LBUTTONUP)
            self.action_invoked.emit(Qt.MouseButton.LeftButton)
        elif btn == Qt.MouseButton.RightButton:
            self.send_action(WM_RBUTTONDOWN)
            self.send_action(WM_RBUTTONUP)
            self.action_invoked.emit(Qt.MouseButton.RightButton)
        elif btn == Qt.MouseButton.MiddleButton:
            self.pinned_changed.emit(self)
            self.action_invoked.emit(Qt.MouseButton.MiddleButton)

        QPushButton.mouseReleaseEvent(self, e)

    @override
    def mouseDoubleClickEvent(self, e: QMouseEvent | None) -> None:
        if e is None:
            return
        self.ignore_next_release = True
        self.send_action(WM_LBUTTONDBLCLK)
        self.action_invoked.emit(Qt.MouseButton.LeftButton)
        QPushButton.mouseDoubleClickEvent(self, e)


class SystrayPopupWidget(BaseWidget):
    validation_schema = SystrayPopupConfig
    _cleanup_hook_registered = False

    def __init__(self, config: SystrayPopupConfig):
        super().__init__(class_name=config.class_name)
        self.config = config

        self.filtered_guids: set[UUID] = set()
        if not self.config.show_battery:
            self.filtered_guids.add(BATTERY_ICON_GUID)
        if not self.config.show_volume:
            self.filtered_guids.add(VOLUME_ICON_GUID)
        if not self.config.show_network:
            self.filtered_guids.add(NETWORK_GUID)

        SystrayPopupIconWidget.icon_size = self.config.icon_size
        SystrayPopupIconWidget.enable_tooltips = self.config.tooltip

        self.icons: list[SystrayPopupIconWidget] = []
        self.current_state: dict[str, IconState] = {}
        self.screen_id: str | None = None
        self._show_alt_label = False
        self._native_menu_seen = False
        self._native_menu_checks = 0

        self._widget_container_layout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(
            self.config.container_padding.left,
            self.config.container_padding.top,
            self.config.container_padding.right,
            self.config.container_padding.bottom,
        )

        self._widget_container = QFrame(self)
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        add_shadow(self._widget_container, self.config.container_shadow.model_dump())
        self.widget_layout.addWidget(self._widget_container)

        self.pinned_widget = QFrame(self)
        self.pinned_layout = QHBoxLayout(self.pinned_widget)
        self.pinned_layout.setSpacing(0)
        self.pinned_layout.setContentsMargins(0, 0, 0, 0)
        self.pinned_widget.setProperty("class", "pinned-container")
        add_shadow(self.pinned_widget, self.config.pinned_shadow.model_dump())

        if self.config.pinned_position == "left":
            self._widget_container_layout.addWidget(self.pinned_widget)

        build_widget_label(
            self,
            self.config.label,
            self.config.label_alt,
            self.config.label_shadow.model_dump(),
        )

        if self.config.pinned_position == "right":
            self._widget_container_layout.addWidget(self.pinned_widget)

        self._popup = self._create_popup()

        self.icon_check_timer = QTimer(self)
        self.icon_check_timer.timeout.connect(self.check_icons)
        self.icon_check_timer.start(5000)

        self.sort_timer = QTimer(self)
        self.sort_timer.timeout.connect(self.sort_icons)
        self.sort_timer.setSingleShot(True)

        self.native_menu_timer = QTimer(self)
        self.native_menu_timer.timeout.connect(self._poll_native_menu)
        self.native_menu_timer.setInterval(120)

        self.register_callback("toggle_menu", self._toggle_menu)
        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("refresh_systray", self.refresh_systray)
        self.register_callback("update_label", self._update_label)

        self.callback_left = self.config.callbacks.on_left
        self.callback_middle = self.config.callbacks.on_middle
        self.callback_right = self.config.callbacks.on_right

        QTimer.singleShot(0, self.setup_client)
        QTimer.singleShot(0, self._update_label)
        QTimer.singleShot(0, self.update_pinned_widget_visibility)

    def _create_popup(self) -> PersistentPopupWidget:
        popup = PersistentPopupWidget(
            self,
            self.config.menu.blur,
            self.config.menu.round_corners,
            self.config.menu.round_corners_type,
            self.config.menu.border_color,
        )
        popup.setProperty("class", "systray-popup-menu")
        add_shadow(popup, self.config.popup_shadow.model_dump())

        main_layout = QVBoxLayout(popup)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea(popup)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setProperty("class", "scroll-area")
        main_layout.addWidget(self.scroll_area)

        self.contents_widget = QWidget(self.scroll_area)
        self.contents_widget.setProperty("class", "contents")
        self.contents_layout = QVBoxLayout(self.contents_widget)
        self.contents_layout.setSpacing(0)
        self.contents_layout.setContentsMargins(6, 6, 6, 6)

        self.empty_label = QLabel("No unpinned tray icons.", self.contents_widget)
        self.empty_label.setProperty("class", "empty-list")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.contents_layout.addWidget(self.empty_label)

        self.grid_widget = QWidget(self.contents_widget)
        self.grid_widget.setProperty("class", "grid")
        self.unpinned_layout = QGridLayout(self.grid_widget)
        self.unpinned_layout.setSpacing(0)
        self.unpinned_layout.setContentsMargins(0, 0, 0, 0)
        self.contents_layout.addWidget(self.grid_widget)

        self.scroll_area.setWidget(self.contents_widget)
        popup.setMinimumWidth(max(140, self.config.grid_columns * (self.config.icon_size + 8)))
        popup.hide()
        return popup

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

        if is_valid_qobject(self._popup) and self._popup.isVisible():
            self._close_menu()
            return

        self._open_menu()

    def _open_menu(self):
        if not is_valid_qobject(self._popup):
            self._popup = self._create_popup()

        self._reflow_unpinned_grid()
        self._popup.adjustSize()

        size_hint = self._popup.sizeHint()
        target_height = min(size_hint.height(), self.config.menu.max_height)
        self._popup.resize(size_hint.width(), target_height)

        self._position_popup_from_anchor()
        self._popup.show()

    def _get_popup_anchor_widget(self) -> QWidget:
        if self.config.menu.anchor == "widget":
            return self

        active = []
        if hasattr(self, "_widgets"):
            active.extend(self._widgets)
        if hasattr(self, "_widgets_alt"):
            active.extend(self._widgets_alt)
        for widget in active:
            if widget.isVisible():
                return widget
        return self

    def _position_popup_from_anchor(self):
        if not is_valid_qobject(self._popup):
            return

        anchor = self._get_popup_anchor_widget()
        anchor_global = anchor.mapToGlobal(QPoint(0, 0))
        anchor_rect = QRect(anchor_global, anchor.size())
        popup_size = self._popup.size()

        offset_left = self.config.menu.offset_left
        offset_top = self.config.menu.offset_top
        alignment = self.config.menu.alignment
        direction = self.config.menu.direction

        if alignment == "left":
            # Open on the left side of the anchor.
            x = anchor_rect.left() - popup_size.width() + offset_left
        elif alignment == "right":
            # Open on the right side of the anchor.
            x = anchor_rect.right() + 1 + offset_left
        else:
            # Center under the anchor.
            x = anchor_rect.left() + (anchor_rect.width() - popup_size.width()) // 2 + offset_left

        if direction == "up":
            y = anchor_rect.top() - popup_size.height() - offset_top
        else:
            y = anchor_rect.bottom() + 1 + offset_top

        screen = QApplication.screenAt(anchor_rect.center())
        if screen:
            geo = screen.geometry()
            x = max(geo.left(), min(x, geo.right() - popup_size.width()))
            y = max(geo.top(), min(y, geo.bottom() - popup_size.height()))

        self._popup.move(x, y)

    def _close_menu(self):
        if self.native_menu_timer.isActive():
            self.native_menu_timer.stop()

        if is_valid_qobject(self._popup):
            self._popup.set_auto_close_enabled(True)
            if self._popup.isVisible() and not self._popup._is_closing:
                self._popup.hide_animated()

    def _start_native_menu_watch(self):
        if not (is_valid_qobject(self._popup) and self._popup.isVisible()):
            return

        self._native_menu_seen = False
        self._native_menu_checks = 0
        self._popup.set_auto_close_enabled(False)
        self.native_menu_timer.start()

    def _poll_native_menu(self):
        self._native_menu_checks += 1
        class_name = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                class_name = win32gui.GetClassName(hwnd)
        except Exception:
            class_name = ""

        if class_name == "#32768":
            self._native_menu_seen = True
            return

        # Menu has appeared and then closed, or fallback timeout:
        # keep popup open and simply restore outside-click autoclose.
        if self._native_menu_seen or self._native_menu_checks >= 25:
            self.native_menu_timer.stop()
            if is_valid_qobject(self._popup):
                self._popup.set_auto_close_enabled(True)

    def _update_label(self):
        total_count = len([icon for icon in self.icons if not icon.isHidden()])
        pinned_count = len([icon for icon in self.icons if icon.is_pinned and not icon.isHidden()])
        unpinned_count = len([icon for icon in self.icons if not icon.is_pinned and not icon.isHidden()])

        active_widgets = self._widgets_alt if self._show_alt_label and hasattr(self, "_widgets_alt") else self._widgets
        active_label_content = self.config.label_alt if self._show_alt_label else self.config.label
        label_parts = [part for part in re.split(r"(<span.*?>.*?</span>)", active_label_content) if part]

        substitutions = {
            "{count}": str(total_count),
            "{pinned_count}": str(pinned_count),
            "{unpinned_count}": str(unpinned_count),
        }

        widget_index = 0
        for part in label_parts:
            if widget_index >= len(active_widgets):
                break

            part = part.strip()
            for token, value in substitutions.items():
                part = part.replace(token, value)

            current_widget = active_widgets[widget_index]
            if "<span" in part and "</span>" in part:
                icon = re.sub(r"<span.*?>|</span>", "", part).strip()
                current_widget.setText(icon)
            else:
                current_widget.setText(part)
            widget_index += 1

    def refresh_systray(self):
        SystrayMonitor.send_taskbar_created()
        logger.debug("Systray popup icons refreshed")

    def setup_client(self):
        self.load_state()

        # Reuse the shared monitor instance used by the standard systray widget.
        from core.widgets.yasb.systray import SystrayWidget

        systray_client, systray_thread = SystrayWidget.get_client_instance()
        systray_client.icon_modified.connect(self.on_icon_modified)
        systray_client.icon_deleted.connect(self.on_icon_deleted)

        app_inst = QApplication.instance()
        if app_inst is not None:
            app_inst.aboutToQuit.connect(self.save_state)
            if not SystrayPopupWidget._cleanup_hook_registered:
                app_inst.aboutToQuit.connect(SystrayWidget._cleanup_threads)
                SystrayPopupWidget._cleanup_hook_registered = True

        if systray_thread is not None and not systray_thread.isRunning():
            systray_thread.start()
            systray_thread.started.connect(self.on_thread_started)
        else:
            QTimer.singleShot(300, SystrayMonitor.send_taskbar_created)

    def on_thread_started(self):
        logger.debug("Systray monitor thread started for popup widget")
        QTimer.singleShot(200, SystrayMonitor.send_taskbar_created)

    @pyqtSlot(IconData)
    def on_icon_modified(self, data: IconData):
        if data.guid in self.filtered_guids:
            return

        icon = self.find_icon(data.guid, data.hWnd, data.uID)
        if icon is None:
            icon = SystrayPopupIconWidget()
            icon.data = IconData()
            icon.pinned_changed.connect(self.on_icon_pinned_changed)
            icon.action_invoked.connect(lambda btn, i=icon: self.on_icon_action_invoked(i, btn))
            self.icons.append(icon)

            id_key = str(data.guid) if data.guid is not None else data.exe_path
            saved_data = self.current_state.get(
                id_key,
                self.current_state.get(data.exe_path, IconState(index=-1, is_pinned=False)),
            )
            add_shadow(icon, self.config.btn_shadow.model_dump())
            icon.is_pinned = saved_data.is_pinned
            if saved_data.is_pinned:
                self.pinned_layout.addWidget(icon)
            else:
                self.unpinned_layout.addWidget(icon)

        self.update_icon_data(icon.data, data)
        icon.update_icon()
        icon.setHidden(data.uFlags & NIF_STATE != 0 and data.dwState == 1)

        self.sort_timer.start(250)
        self.update_pinned_widget_visibility()
        self._update_label()

    @pyqtSlot(IconData)
    def on_icon_deleted(self, data: IconData) -> None:
        icon = self.find_icon(data.guid, data.hWnd, data.uID)
        if icon is None:
            return

        self.icons.remove(icon)
        self.pinned_layout.removeWidget(icon)
        self.unpinned_layout.removeWidget(icon)
        icon.deleteLater()

        self._reflow_unpinned_grid()
        self.update_pinned_widget_visibility()
        self._update_label()

    @pyqtSlot(object)
    def on_icon_pinned_changed(self, icon: SystrayPopupIconWidget):
        if icon.is_pinned:
            self.pinned_layout.removeWidget(icon)
            icon.is_pinned = False
        else:
            self.unpinned_layout.removeWidget(icon)
            self.pinned_layout.addWidget(icon)
            icon.is_pinned = True

        icon.show()
        self._reflow_unpinned_grid()
        self.save_state()
        self.update_pinned_widget_visibility()
        self._update_label()

    @pyqtSlot(object, object)
    def on_icon_action_invoked(self, icon: SystrayPopupIconWidget, button: object):
        if button == Qt.MouseButton.RightButton and not icon.is_pinned:
            self._start_native_menu_watch()
            return

        if button in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._close_menu()

    def find_icon(self, uuid: UUID | None, hwnd: int, uID: int) -> SystrayPopupIconWidget | None:
        if uuid is not None:
            for icon in self.icons:
                if icon.data is None or icon.data.guid is None:
                    continue
                if icon.data.guid == uuid:
                    return icon

        for icon in self.icons:
            if icon.data is None:
                continue
            if icon.data.hWnd == hwnd and icon.data.uID == uID:
                return icon
        return None

    def check_icons(self):
        icons_changed = False
        for icon in self.icons[:]:
            if icon.data is not None and not IsWindow(icon.data.hWnd):
                self.icons.remove(icon)
                self.pinned_layout.removeWidget(icon)
                self.unpinned_layout.removeWidget(icon)
                icon.deleteLater()
                icons_changed = True

        if icons_changed:
            self._reflow_unpinned_grid()
            self.update_pinned_widget_visibility()
            self._update_label()

    def update_icon_data(self, old_data: IconData | None, new_data: IconData):
        if old_data is None:
            return

        direct_attributes = [
            "message_type",
            "hWnd",
            "uID",
            "uFlags",
            "icon_image",
            "exe",
            "exe_path",
        ]
        for attr in direct_attributes:
            if attr in ("hWnd", "uID"):
                continue
            setattr(old_data, attr, getattr(new_data, attr))
        old_data.hWnd = new_data.hWnd or old_data.hWnd
        old_data.uID = new_data.uID or old_data.uID
        if 0 < new_data.uVersion <= 4:
            old_data.uVersion = new_data.uVersion

        flag_dependent_attrs = {
            NIF_MESSAGE: ["uCallbackMessage"],
            NIF_ICON: ["hIcon"],
            NIF_TIP: ["szTip"],
            NIF_STATE: ["dwState", "dwStateMask"],
            NIF_GUID: ["guid"],
            NIF_INFO: ["dwInfoFlags", "szInfoTitle", "szInfo", "uTimeout"],
        }

        for flag, attrs in flag_dependent_attrs.items():
            if new_data.uFlags & flag:
                for attr in attrs:
                    setattr(old_data, attr, getattr(new_data, attr))

    def _visible_unpinned_icons(self) -> list[SystrayPopupIconWidget]:
        return [icon for icon in self.icons if not icon.is_pinned and not icon.isHidden()]

    def _reflow_unpinned_grid(self, ordered_icons: list[SystrayPopupIconWidget] | None = None):
        for i in reversed(range(self.unpinned_layout.count())):
            item = self.unpinned_layout.itemAt(i)
            if item and (w := item.widget()):
                self.unpinned_layout.removeWidget(w)

        icons = ordered_icons if ordered_icons is not None else self._visible_unpinned_icons()
        for index, icon in enumerate(icons):
            row = index // self.config.grid_columns
            col = index % self.config.grid_columns
            self.unpinned_layout.addWidget(icon, row, col)
            icon.show()

        self.empty_label.setVisible(len(icons) == 0)

    def is_layout_empty(self, layout: QLayout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and (w := item.widget()) and not w.isHidden():
                return False
        return True

    def update_pinned_widget_visibility(self):
        self.pinned_widget.setVisible(not self.is_layout_empty(self.pinned_layout))

    def sort_icons(self):
        pinned = [icon for icon in self.icons if icon.is_pinned and not icon.isHidden()]
        unpinned = [icon for icon in self.icons if not icon.is_pinned and not icon.isHidden()]

        def get_sort_index(widget: SystrayPopupIconWidget):
            if widget.data is None:
                return 9999
            if widget.data.guid is not None:
                index = self.current_state.get(str(widget.data.guid))
            else:
                index = self.current_state.get(widget.data.exe_path)
            return index.index if index is not None else 9999

        pinned.sort(key=get_sort_index)
        unpinned.sort(key=get_sort_index)

        for i in reversed(range(self.pinned_layout.count())):
            item = self.pinned_layout.itemAt(i)
            if item and (w := item.widget()):
                self.pinned_layout.removeWidget(w)
        for icon in pinned:
            self.pinned_layout.addWidget(icon)
            icon.show()

        self._reflow_unpinned_grid(unpinned)
        self.update_current_state()
        self.update_pinned_widget_visibility()
        self._update_label()

    def update_current_state(self):
        widgets_state: dict[str, Any] = {}
        for icon in self.icons:
            if icon.data is None or icon.isHidden():
                continue

            if icon.is_pinned:
                index = self.pinned_layout.indexOf(icon)
            else:
                index = self.unpinned_layout.indexOf(icon)

            icon_id = None if icon.data.guid is None else str(icon.data.guid)
            widgets_state[icon_id or icon.data.exe_path] = IconState(is_pinned=icon.is_pinned, index=index)

        self.current_state |= widgets_state

    def save_state(self):
        self.update_current_state()
        self.get_screen_id()
        file_path = app_data_path(f"systray_popup_state_{self.screen_id}.json")

        saved_state: dict[str, Any] = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                saved_state = json.load(f)
        except json.JSONDecodeError:
            logger.debug("State file decode error. Ignoring.")
        except FileNotFoundError:
            logger.debug("Popup state file not found.")

        new_state = saved_state | {k: v.__dict__ for k, v in self.current_state.items()}
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(new_state, indent=2))

    def load_state(self):
        self.get_screen_id()
        file_path = app_data_path(f"systray_popup_state_{self.screen_id}.json")
        self.current_state = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                for k, v in state.items():
                    self.current_state[k] = IconState.from_dict(v)
        except json.JSONDecodeError:
            logger.debug("Popup state file decode error. Ignoring.")
        except FileNotFoundError:
            logger.debug("Popup state file not found.")

    def get_screen_id(self):
        screen = self.screen()
        if screen is not None:
            raw_id = f"{screen.manufacturer()}{screen.name()}{screen.serialNumber()}".upper()
            self.screen_id = re.sub(r"\W+", "", raw_id)
            return self.screen_id
