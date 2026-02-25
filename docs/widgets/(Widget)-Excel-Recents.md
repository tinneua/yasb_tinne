# Excel Recents Widget Configuration

| Option | Type | Default Value | Description |
|---|---|---|---|
| `label` | string | `"<span>\uf1c3</span>"` | Primary label template. |
| `label_alt` | string | `"<span>\uf1c3</span> {count}"` | Alternate label template, supports `{count}`. |
| `class_name` | string | `""` | Additional CSS class for the widget. |
| `max_items` | integer | `10` | Maximum number of entries shown (hard max `20`). |
| `max_title_length` | integer | `40` | Maximum title characters before truncation. |
| `max_path_length` | integer | `60` | Maximum location characters before truncation. |
| `hide_missing_files` | boolean | `true` | Hide missing local files. URL entries are still allowed. |
| `favorites_path` | string | `""` | Path to favorites JSON. Empty uses `~/.config/yasb/excel_recents_favorites.json`. |
| `update_interval` | integer | `300000` | Refresh interval in ms (`0` disables timer refresh). |
| `menu` | dict | See below | Popup menu options. |
| `icons` | dict | See below | Icons for file/favorites/pinned markers. |
| `callbacks` | dict | `{ on_left: "toggle_menu", on_middle: "toggle_label", on_right: "do_nothing" }` | Mouse callbacks. |
| `animation` | dict | `{ enabled: true, type: "fadeInOut", duration: 200 }` | Widget animation settings. |
| `container_padding` | dict | `{ top: 0, left: 0, bottom: 0, right: 0 }` | Padding for label container. |
| `label_shadow` | dict | default shadow config | Label shadow options. |
| `container_shadow` | dict | default shadow config | Container shadow options. |

### Menu Options

| Option | Type | Default | Description |
|---|---|---|---|
| `blur` | boolean | `true` | Enable popup blur. |
| `round_corners` | boolean | `true` | Enable rounded corners. |
| `round_corners_type` | string | `"normal"` | Corner style (`normal`, `small`). |
| `border_color` | string | `"System"` | Border color. |
| `alignment` | string | `"center"` | Horizontal popup alignment. |
| `direction` | string | `"down"` | Popup open direction. |
| `offset_top` | integer | `6` | Vertical popup offset. |
| `offset_left` | integer | `0` | Horizontal popup offset. |

### Icons

| Option | Type | Default |
|---|---|---|
| `file` | string | `"\uf1c3"` |
| `pinned` | string | `"\uf08d"` |
| `favorite_on` | string | `"\uf005"` |
| `favorite_off` | string | `"\uf006"` |

## Behavior

- Data source: Excel MRU from Windows registry (user/account scoped with fallback paths).
- Ordering:
  1. Excel-native pinned entries
  2. User favorites
  3. Remaining recents
- Item interactions:
  - left click: open item
  - middle click: toggle favorite
  - right click: open containing folder (or base URL for web entries)

## Example Configuration

```yaml
excel-recents:
  type: "yasb.excel_recents.ExcelRecentsWidget"
  options:
    label: "<span>\uf1c3</span>"
    label_alt: "<span>\uf1c3</span> {count}"
    max_items: 10
    hide_missing_files: true
    update_interval: 300000
    menu:
      blur: true
      round_corners: true
      round_corners_type: "normal"
      border_color: "System"
      alignment: "center"
      direction: "down"
      offset_top: 6
      offset_left: 0
    icons:
      file: "\uf1c3"
      pinned: "\uf08d"
      favorite_on: "\uf005"
      favorite_off: "\uf006"
    callbacks:
      on_left: "toggle_menu"
      on_middle: "toggle_label"
      on_right: "do_nothing"
```

## Available Styles

```css
.excel-recents-widget {}
.excel-recents-widget .label {}
.excel-recents-widget .icon {}

.excel-recents-menu {}
.excel-recents-menu .item {}
.excel-recents-menu .item:hover {}
.excel-recents-menu .title {}
.excel-recents-menu .path {}
.excel-recents-menu .file-icon {}
.excel-recents-menu .favorite-icon {}
.excel-recents-menu .empty-list {}
.excel-recents-menu .scroll-area {}
```

