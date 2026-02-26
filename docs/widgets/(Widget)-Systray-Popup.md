# Systray Popup Widget

| Option | Type | Default | Description |
|---|---|---|---|
| `label` | string | `"<span>Tray</span>"` | Main label text/icon template. |
| `label_alt` | string | `"<span>Tray</span> {unpinned_count}"` | Alternate label template. Supports `{count}`, `{pinned_count}`, `{unpinned_count}`. |
| `class_name` | string | `"systray-popup-widget"` | CSS class for the base widget. |
| `pinned_position` | string | `"right"` | Inline pinned icon position relative to label (`left`, `right`). |
| `icon_size` | integer | `16` | Tray icon size (8-64). |
| `tooltip` | boolean | `true` | Show tooltip for tray icons. |
| `show_battery` | boolean | `false` | Include battery icon from the original tray. |
| `show_volume` | boolean | `false` | Include volume icon from the original tray. |
| `show_network` | boolean | `false` | Include network icon from the original tray. |
| `grid_columns` | integer | `8` | Number of columns in popup grid (1-32). |
| `menu` | dict | see below | Popup menu positioning and appearance. |
| `callbacks` | dict | `{ on_left: "toggle_menu", on_middle: "toggle_label", on_right: "do_nothing" }` | Widget click callbacks. |
| `animation` | dict | standard animation config | Label/menu animation options. |
| `container_padding` | dict | standard padding config | Padding for inline widget container. |
| `container_shadow` | dict | standard shadow config | Shadow for inline container. |
| `label_shadow` | dict | standard shadow config | Shadow for label widgets. |
| `pinned_shadow` | dict | standard shadow config | Shadow for pinned inline container. |
| `popup_shadow` | dict | standard shadow config | Shadow for popup window. |
| `btn_shadow` | dict | standard shadow config | Shadow for icon buttons. |

## Menu Options

| Option | Type | Default | Description |
|---|---|---|---|
| `blur` | boolean | `true` | Enable popup blur. |
| `round_corners` | boolean | `true` | Enable rounded corners. |
| `round_corners_type` | string | `"normal"` | Rounded corner style (`normal`, `small`). |
| `border_color` | string | `"System"` | Popup border color. |
| `anchor` | string | `"label"` | Anchor target for positioning (`label`, `widget`). |
| `alignment` | string | `"right"` | Horizontal placement relative to selected `anchor` (`left` = left side, `center` = centered, `right` = right side). |
| `direction` | string | `"down"` | Popup direction (`up`, `down`). |
| `offset_top` | integer | `6` | Vertical offset in pixels. |
| `offset_left` | integer | `0` | Horizontal offset in pixels. |
| `max_height` | integer | `260` | Max popup height before vertical scrolling. |

## Behavior

- Pinned icons stay inline in the bar.
- Unpinned icons are shown in a popup grid.
- Middle click on an icon toggles pin/unpin.
- Left click executes icon action and closes popup.
- Right click opens native tray menu, keeps popup alive while the menu is open, then closes popup.
- State is persisted per screen in `LOCALAPPDATA\\YASB\\systray_popup_state_<screen>.json`.

## Example Configuration

```yaml
systray-popup:
  type: "tinneua.systray_popup.SystrayPopupWidget"
  options:
    label: "<span>Tray</span>"
    label_alt: "<span>Tray</span> {unpinned_count}"
    pinned_position: "right"
    icon_size: 16
    grid_columns: 8
    show_battery: false
    show_volume: false
    show_network: false
    menu:
      blur: true
      round_corners: true
      round_corners_type: "normal"
      border_color: "System"
      anchor: "label"
      alignment: "right"
      direction: "down"
      offset_top: 6
      offset_left: 0
      max_height: 260
    callbacks:
      on_left: "toggle_menu"
      on_middle: "toggle_label"
      on_right: "do_nothing"
```

## Styles

```css
.systray-popup-widget {}
.systray-popup-widget .widget-container {}
.systray-popup-widget .label {}
.systray-popup-widget .label.alt {}
.systray-popup-widget .pinned-container {}
.systray-popup-widget .button {}

.systray-popup-menu {}
.systray-popup-menu .scroll-area {}
.systray-popup-menu .contents {}
.systray-popup-menu .grid {}
.systray-popup-menu .button {}
.systray-popup-menu .empty-list {}
```
