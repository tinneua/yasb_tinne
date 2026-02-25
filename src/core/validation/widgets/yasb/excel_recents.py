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


class ExcelRecentsMenuConfig(CustomBaseModel):
    blur: bool = True
    round_corners: bool = True
    round_corners_type: Literal["normal", "small"] = "normal"
    border_color: str = "System"
    alignment: str = "center"
    direction: str = "down"
    offset_top: int = 6
    offset_left: int = 0


class ExcelRecentsIconsConfig(CustomBaseModel):
    file: str = "\uf1c3"
    pinned: str = "\uf08d"
    favorite_on: str = "\uf005"
    favorite_off: str = "\uf006"


class ExcelRecentsCallbacksConfig(CallbacksConfig):
    on_left: str = "toggle_menu"
    on_middle: str = "toggle_label"
    on_right: str = "do_nothing"


class ExcelRecentsConfig(CustomBaseModel):
    label: str = "<span>\uf1c3</span>"
    label_alt: str = "<span>\uf1c3</span> {count}"
    class_name: str = ""
    max_items: int = Field(default=10, ge=1, le=20)
    max_title_length: int = Field(default=40, ge=4, le=300)
    max_path_length: int = Field(default=60, ge=4, le=500)
    hide_missing_files: bool = True
    favorites_path: str = ""
    update_interval: int = Field(default=300000, ge=0)
    menu: ExcelRecentsMenuConfig = ExcelRecentsMenuConfig()
    icons: ExcelRecentsIconsConfig = ExcelRecentsIconsConfig()
    animation: AnimationConfig = AnimationConfig()
    container_padding: PaddingConfig = PaddingConfig()
    label_shadow: ShadowConfig = ShadowConfig()
    container_shadow: ShadowConfig = ShadowConfig()
    keybindings: list[KeybindingConfig] = []
    callbacks: ExcelRecentsCallbacksConfig = ExcelRecentsCallbacksConfig()

