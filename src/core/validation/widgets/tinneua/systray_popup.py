from typing import Literal

from pydantic import Field

from core.validation.widgets.base_model import (
    AnimationConfig,
    CallbacksConfig,
    CustomBaseModel,
    KeybindingConfig,
    PaddingConfig,
    ShadowConfig,
)


class SystrayPopupMenuConfig(CustomBaseModel):
    blur: bool = True
    round_corners: bool = True
    round_corners_type: Literal["normal", "small"] = "normal"
    border_color: str = "System"
    anchor: Literal["label", "widget"] = "label"
    alignment: Literal["left", "center", "right"] = "right"
    direction: Literal["up", "down"] = "down"
    offset_top: int = 6
    offset_left: int = 0
    max_height: int = Field(default=260, ge=80, le=1200)


class SystrayPopupCallbacksConfig(CallbacksConfig):
    on_left: str = "toggle_menu"
    on_middle: str = "toggle_label"
    on_right: str = "do_nothing"


class SystrayPopupConfig(CustomBaseModel):
    label: str = "<span>Tray</span>"
    label_alt: str = "<span>Tray</span> {unpinned_count}"
    class_name: str = "systray-popup-widget"
    pinned_position: Literal["left", "right"] = "right"
    icon_size: int = Field(default=16, ge=8, le=64)
    tooltip: bool = True
    show_battery: bool = False
    show_volume: bool = False
    show_network: bool = False
    grid_columns: int = Field(default=8, ge=1, le=32)
    menu: SystrayPopupMenuConfig = SystrayPopupMenuConfig()
    animation: AnimationConfig = AnimationConfig()
    container_padding: PaddingConfig = PaddingConfig()
    container_shadow: ShadowConfig = ShadowConfig()
    label_shadow: ShadowConfig = ShadowConfig()
    pinned_shadow: ShadowConfig = ShadowConfig()
    popup_shadow: ShadowConfig = ShadowConfig()
    btn_shadow: ShadowConfig = ShadowConfig()
    callbacks: SystrayPopupCallbacksConfig = SystrayPopupCallbacksConfig()
    keybindings: list[KeybindingConfig] = []
