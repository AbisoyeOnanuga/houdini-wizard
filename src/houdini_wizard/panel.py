"""Parameter guide for the node that is open.

The window stays up while Houdini is used. It follows the selection.
Pictures, menu choices, and number ranges come from this install.
"""

from __future__ import annotations

from houdini_wizard.context import build_study, image_bytes
from houdini_wizard.help_file import Section, installed_help, library_catalog

_WINDOW = None
_CALLBACK = None


def show_panel(
    sections: tuple[Section, ...] | list[Section],
    scene: dict,
    focus_heading: str,
    extra_note: str = "",
    refresh=None,
) -> None:
    try:
        _qt_panel(sections, scene, focus_heading, extra_note, refresh)
    except Exception:
        _plain_panel(sections, scene, focus_heading, extra_note)


def _qt_panel(sections, scene: dict, focus_heading: str, extra_note: str, refresh) -> None:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    import hou

    study = build_study(sections, scene, focus_heading)
    if scene.get("service"):
        study["service"] = scene["service"]
    if extra_note:
        study["note"] = f"{extra_note} {study['note']}".strip()

    window = _window(QtWidgets, QtCore, QtGui, hou)
    window.present(study, raise_window=True)
    _follow(hou, window, refresh)


def show_library(hfs: str, refresh=None) -> None:
    """Open the help library. A later node selection replaces this view."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    import hou

    window = _window(QtWidgets, QtCore, QtGui, hou)
    window.present(_library_study(hfs), raise_window=True)
    _follow(hou, window, refresh)


def _window(widgets, core, gui, hou):
    global _WINDOW
    if _WINDOW is not None:
        return _WINDOW
    flags = core.Qt.Window | core.Qt.WindowMinimizeButtonHint | core.Qt.WindowMaximizeButtonHint | core.Qt.WindowCloseButtonHint
    dialog = widgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowFlags(flags)
    dialog.setWindowModality(core.Qt.NonModal)
    dialog.setAttribute(core.Qt.WA_QuitOnClose, False)
    dialog.setMinimumSize(720, 360)
    dialog.resize(960, 720)
    dialog.setSizeGripEnabled(True)
    dialog._fitted = False
    dialog._hou = hou
    dialog._user_pos = None
    dialog._placing = False
    dialog._gui = gui
    dialog._widgets = widgets
    dialog._core = core
    dialog._zoom = 1.0
    dialog._theme = "dark"
    dialog._study = None
    dialog._anchors = {}
    dialog._folder_index = {}
    dialog._parm_folder = {}
    dialog.tabs = None

    outer = widgets.QVBoxLayout(dialog)
    outer.setContentsMargins(12, 10, 12, 10)
    outer.setSpacing(8)

    bar = widgets.QHBoxLayout()
    dialog.library_button = widgets.QPushButton("Library")
    dialog.library_button.setToolTip("Browse the help that shipped with this Houdini")
    dialog.nav_button = widgets.QPushButton("Sections")
    dialog.nav_button.setCheckable(True)
    dialog.nav_button.setChecked(True)
    dialog.nav_button.setToolTip("Hide or show the section list")
    dialog.zoom_out = widgets.QPushButton("A−")
    dialog.zoom_out.setObjectName("zoomOut")
    dialog.zoom_out.setToolTip("Smaller text, in steps of 10%")
    dialog.zoom_label = widgets.QLabel("100%")
    dialog.zoom_label.setObjectName("zoom")
    dialog.zoom_slider = widgets.QSlider(core.Qt.Horizontal)
    dialog.zoom_slider.setRange(70, 180)
    dialog.zoom_slider.setValue(100)
    dialog.zoom_slider.setFixedWidth(120)
    dialog.zoom_slider.setToolTip("Text size")
    dialog.zoom_in = widgets.QPushButton("A+")
    dialog.zoom_in.setObjectName("zoomIn")
    dialog.zoom_in.setToolTip("Larger text, in steps of 10%")
    dialog.theme_button = widgets.QPushButton("Light")
    dialog.theme_button.setToolTip("Switch the panel colors")
    dialog.close_button = widgets.QPushButton("Exit")
    dialog.close_button.setToolTip("Close the panel")
    bar.addWidget(dialog.library_button)
    bar.addWidget(dialog.nav_button)
    dialog.library_button.clicked.connect(lambda: _open_library(dialog))
    bar.addWidget(dialog.zoom_out)
    bar.addWidget(dialog.zoom_label)
    bar.addWidget(dialog.zoom_slider)
    bar.addWidget(dialog.zoom_in)
    bar.addStretch(1)
    bar.addWidget(dialog.theme_button)
    bar.addWidget(dialog.close_button)
    outer.addLayout(bar)
    dialog.zoom_out.clicked.connect(lambda: _step_zoom(dialog, -10))
    dialog.zoom_in.clicked.connect(lambda: _step_zoom(dialog, 10))
    dialog.zoom_slider.valueChanged.connect(lambda value: _set_zoom(dialog, value, snap=False))
    dialog.nav_button.toggled.connect(lambda open_nav: _toggle_nav(dialog, open_nav))
    dialog.theme_button.clicked.connect(lambda: _toggle_theme(dialog))
    dialog.close_button.clicked.connect(dialog.close)

    dialog.outline = widgets.QListWidget()
    dialog.outline.setObjectName("outline")
    dialog.outline.setMinimumWidth(0)
    dialog.outline.setHorizontalScrollBarPolicy(core.Qt.ScrollBarAlwaysOff)
    dialog.outline.setFrameShape(widgets.QFrame.NoFrame)
    dialog.outline.currentRowChanged.connect(lambda row: _on_outline(dialog, row))

    dialog.scroll = widgets.QScrollArea()
    dialog.scroll.setObjectName("guideScroll")
    dialog.scroll.setWidgetResizable(True)
    dialog.scroll.setFrameShape(widgets.QFrame.NoFrame)
    dialog.scroll.setHorizontalScrollBarPolicy(core.Qt.ScrollBarAlwaysOff)
    dialog.page = widgets.QWidget()
    dialog.page.setObjectName("page")
    dialog.page_layout = widgets.QVBoxLayout(dialog.page)
    dialog.page_layout.setContentsMargins(2, 2, 8, 8)
    dialog.page_layout.setSpacing(10)
    dialog.scroll.setWidget(dialog.page)

    dialog.splitter = widgets.QSplitter(core.Qt.Horizontal)
    dialog.splitter.addWidget(dialog.outline)
    dialog.splitter.addWidget(dialog.scroll)
    dialog.splitter.setStretchFactor(1, 1)
    dialog.splitter.setCollapsible(0, True)
    dialog.splitter.setSizes([210, 720])
    dialog._nav_width = 210
    outer.addWidget(dialog.splitter, 1)

    def moveEvent(event) -> None:
        widgets.QDialog.moveEvent(dialog, event)
        if dialog._placing or not dialog.isVisible():
            return
        dialog._user_pos = dialog.pos()
        dialog.setAttribute(core.Qt.WA_Moved, True)

    def present(study: dict, raise_window: bool) -> None:
        previous = dialog._study
        reveal = raise_window or _selected_name(previous) != _selected_name(study)
        dialog._study = study
        if study.get("hfs"):
            dialog._hfs = study["hfs"]
        keep = dialog._user_pos
        dialog._placing = True
        try:
            _fill(dialog, study, reveal=reveal)
            dialog.setWindowTitle(study.get("type_label") or "Houdini wizard")
            if not dialog._fitted:
                _fit(dialog)
                dialog._fitted = True
            if dialog.isMinimized():
                return
            if raise_window or dialog.isVisible():
                dialog.show()
            if keep is not None:
                dialog.move(keep)
                dialog.setAttribute(core.Qt.WA_Moved, True)
            if raise_window:
                dialog.raise_()
                dialog.activateWindow()
        finally:
            dialog._placing = False

    def closeEvent(event) -> None:
        widgets.QDialog.closeEvent(dialog, event)

    dialog.moveEvent = moveEvent
    dialog.present = present
    dialog.closeEvent = closeEvent
    _restyle(dialog)
    _WINDOW = dialog
    return dialog


def _fill(dialog, study: dict, reveal: bool = False) -> None:
    if study.get("kind") == "library":
        _fill_library(dialog, study)
        return
    widgets = dialog._widgets
    layout = dialog.page_layout
    _empty_layout(layout)
    for child in list(dialog.page.children()):
        if child is layout or not hasattr(child, "hide"):
            continue
        child.hide()
        child.setParent(None)
        child.deleteLater()

    dialog._anchors = {}
    dialog._folder_index = {}
    dialog._parm_folder = {}
    dialog.tabs = None
    dialog.outline.blockSignals(True)
    dialog.outline.clear()

    header = widgets.QWidget()
    header_layout = widgets.QHBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    icon = _icon_label(dialog, study.get("icon") or "")
    if icon is not None:
        header_layout.addWidget(icon)
    titles = widgets.QVBoxLayout()
    where = widgets.QLabel(study.get("where") or "")
    where.setObjectName("where")
    where.setWordWrap(True)
    title = widgets.QLabel(study.get("type_label") or "")
    title.setObjectName("title")
    title.setWordWrap(True)
    summary = widgets.QLabel(study.get("summary") or "")
    summary.setObjectName("summary")
    summary.setWordWrap(True)
    path = widgets.QLabel(study.get("path") or "")
    path.setObjectName("path")
    path.setWordWrap(True)
    titles.addWidget(where)
    titles.addWidget(title)
    if study.get("summary"):
        titles.addWidget(summary)
    titles.addWidget(path)
    header_layout.addLayout(titles, 1)
    layout.addWidget(header)
    _mark(dialog, "section:overview", header, "Overview")
    if study.get("service"):
        layout.addWidget(_service_banner(widgets, study["service"]))

    if study.get("error"):
        layout.addWidget(_callout(widgets, study["error"], "error"))
    if study.get("callout"):
        layout.addWidget(_callout(widgets, study["callout"], "callout"))
    if study.get("note"):
        note = widgets.QLabel(study["note"])
        note.setObjectName("note")
        note.setWordWrap(True)
        layout.addWidget(note)

    if not study.get("library_page"):
        wire_host = widgets.QWidget()
        columns = widgets.QHBoxLayout(wire_host)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.addWidget(_ends_box(widgets, "Node input", study.get("inputs") or [], "No input on this node."))
        columns.addWidget(_ends_box(widgets, "Node output", study.get("outputs") or [], "No output on this node."))
        layout.addWidget(wire_host)
        _mark(dialog, "section:wires", wire_host, "Node input")

    if study.get("steps"):
        heading = _section_label(widgets, "How to use it")
        layout.addWidget(heading)
        _mark(dialog, "section:steps", heading, "How to use it")
        for index, step in enumerate(study["steps"], start=1):
            line = widgets.QLabel(f"{index}.  {step}")
            line.setWordWrap(True)
            line.setObjectName("step")
            layout.addWidget(line)

    if study.get("figures"):
        heading = _section_label(widgets, "What the choices look like")
        layout.addWidget(heading)
        _mark(dialog, "section:figures", heading, "Pictures")
        for figure in study["figures"]:
            layout.addWidget(_figure_pixmaps(dialog, study.get("hfs") or "", figure))

    heading = _section_label(widgets, "Parameters")
    layout.addWidget(heading)
    _mark(dialog, "section:parameters", heading, "Parameters")
    intro = widgets.QLabel("The parameters of this node are listed below. A guide to adjusting their values is included.")
    intro.setObjectName("intro")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    groups = _groups(study.get("parameters") or [])
    chosen = ""
    seen_main = False
    if len(groups) > 1:
        dialog.tabs = widgets.QTabWidget()
        dialog.tabs.setDocumentMode(True)
        for index, (folder, rows) in enumerate(groups):
            if folder:
                label = folder
            elif seen_main:
                label = "More"
            else:
                label = "Main"
                seen_main = True
            page = widgets.QWidget()
            page_layout = widgets.QVBoxLayout(page)
            page_layout.setContentsMargins(8, 8, 8, 8)
            page_layout.setSpacing(8)
            dialog.tabs.addTab(page, label)
            dialog._folder_index[index] = index
            _outline_item(dialog, f"tab:{index}", label, 0)
            chosen = _add_parameters(dialog, page_layout, rows, index) or chosen
            page_layout.addStretch(1)
        dialog._anchors["section:parameters"] = dialog.tabs
        layout.addWidget(dialog.tabs)
        if chosen:
            dialog.tabs.setCurrentIndex(dialog._parm_folder.get(chosen, 0))
    else:
        rows = groups[0][1] if groups else []
        chosen = _add_parameters(dialog, layout, rows, "") or chosen
        if not rows:
            empty = widgets.QLabel("This help file has no parameter list.")
            empty.setWordWrap(True)
            layout.addWidget(empty)

    if study.get("related_nodes"):
        heading = _section_label(widgets, "Use with")
        layout.addWidget(heading)
        _mark(dialog, "section:next", heading, "Use with")
        hint = widgets.QLabel(
            "Houdini’s help browser recommends reading these next. "
            "They can be used with or after this node, so you can decide what you may need next for your project."
        )
        hint.setObjectName("intro")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for node in study["related_nodes"]:
            layout.addWidget(_help_link(dialog, node["label"], node["help"]))
            if node.get("note"):
                why = widgets.QLabel(node["note"])
                why.setObjectName("nextWhy")
                why.setWordWrap(True)
                layout.addWidget(why)

    if study.get("cache"):
        heading = _section_label(widgets, "Keep working while it cooks")
        layout.addWidget(heading)
        _mark(dialog, "section:cache", heading, "Keep working")
        cache = widgets.QLabel(study["cache"])
        cache.setObjectName("cache")
        cache.setWordWrap(True)
        layout.addWidget(cache)

    layout.addStretch(1)
    dialog.outline.blockSignals(False)
    if reveal and chosen:
        _activate(dialog, chosen)


def _groups(parameters: list[dict]) -> list[tuple[str, list[dict]]]:
    """One tab per top-level folder. Nested folders stay inside that tab."""
    groups: list[tuple[str, list[dict]]] = []
    for row in parameters:
        path = tuple(row.get("groups") or ())
        folder = path[0] if path else (row.get("folder") or "")
        if not groups or groups[-1][0] != folder:
            groups.append((folder, []))
        groups[-1][1].append(row)
    return groups


def _add_parameters(dialog, layout, rows: list[dict], tab) -> str:
    """Lay parameters in pane order, with a heading for each nested folder."""
    widgets = dialog._widgets
    chosen = ""
    shown: tuple[str, ...] = ()
    for row in rows:
        path = tuple(row.get("groups") or ())
        nested = path[1:]
        shared = 0
        while shared < len(shown) and shared < len(nested) and shown[shared] == nested[shared]:
            shared += 1
        for index in range(shared, len(nested)):
            head = widgets.QLabel(nested[index])
            head.setObjectName("folderHead")
            head.setContentsMargins((index + 1) * 14, 10, 0, 0)
            layout.addWidget(head)
            _outline_item(dialog, f"folder:{tab}:{nested[index]}", nested[index], index + 1)
        shown = nested
        depth = len(nested)
        card = _parameter(widgets, row, depth)
        layout.addWidget(card)
        key = f"parm:{row['name']}:{path}"
        dialog._anchors[key] = card
        dialog._parm_folder[key] = tab
        _outline_item(dialog, key, row["name"], depth + 1)
        if row.get("selected"):
            chosen = key
    return chosen


def _mark(dialog, key: str, widget, label: str, depth: int = 0) -> None:
    dialog._anchors[key] = widget
    _outline_item(dialog, key, label, depth)


def _outline_item(dialog, key: str, label: str, depth: int) -> None:
    item = dialog._widgets.QListWidgetItem(("    " * depth) + label)
    item.setData(dialog._core.Qt.UserRole, key)
    dialog.outline.addItem(item)


def _library_study(hfs: str) -> dict:
    return {
        "kind": "library",
        "type_label": "Help library",
        "where": "Help that shipped with this Houdini.",
        "summary": "Open any page here. Select a node in the network and this window follows it.",
        "hfs": hfs,
        "catalog": library_catalog(hfs),
    }


def _open_library(dialog) -> None:
    hou = getattr(dialog, "_hou", None)
    if hou is not None:
        try:
            from houdini_wizard.shelf import hold_for_browse

            hold_for_browse(hou)
        except Exception:
            pass
    hfs = getattr(dialog, "_hfs", "") or ""
    if not hfs and hou is not None:
        try:
            hfs = hou.getenv("HFS") or ""
        except Exception:
            hfs = ""
    dialog.present(_library_study(hfs), raise_window=False)


def _fill_library(dialog, study: dict) -> None:
    widgets = dialog._widgets
    layout = dialog.page_layout
    _empty_layout(layout)
    for child in list(dialog.page.children()):
        if child is layout or not hasattr(child, "hide"):
            continue
        child.hide()
        child.setParent(None)
        child.deleteLater()
    dialog._anchors = {}
    dialog.tabs = None
    dialog._catalog = study.get("catalog") or []
    dialog._library_folder = dialog._catalog[0]["folder"] if dialog._catalog else ""
    dialog._library_query = ""
    dialog.outline.blockSignals(True)
    dialog.outline.clear()
    where = widgets.QLabel(study.get("where") or "")
    where.setObjectName("where")
    where.setWordWrap(True)
    title = widgets.QLabel(study.get("type_label") or "")
    title.setObjectName("title")
    summary = widgets.QLabel(study.get("summary") or "")
    summary.setObjectName("summary")
    summary.setWordWrap(True)
    layout.addWidget(where)
    layout.addWidget(title)
    layout.addWidget(summary)
    dialog.library_search = widgets.QLineEdit()
    dialog.library_search.setObjectName("librarySearch")
    dialog.library_search.setPlaceholderText("Search the help library")
    dialog.library_search.textChanged.connect(lambda text, dialog=dialog: _search_library(dialog, text))
    layout.addWidget(dialog.library_search)
    dialog.library_count = widgets.QLabel("")
    dialog.library_count.setObjectName("intro")
    dialog.library_count.setWordWrap(True)
    layout.addWidget(dialog.library_count)
    dialog.library_list = widgets.QListWidget()
    dialog.library_list.setObjectName("libraryList")
    dialog.library_list.setUniformItemSizes(True)
    dialog.library_list.setFrameShape(widgets.QFrame.NoFrame)
    dialog.library_list.setMinimumHeight(520)
    dialog.library_list.itemClicked.connect(lambda item, dialog=dialog: _open_catalog_node(dialog, item))
    layout.addWidget(dialog.library_list)
    for group in dialog._catalog:
        _outline_item(dialog, f"cat:{group['folder']}", group["label"], 0)
    if dialog.outline.count():
        dialog.outline.setCurrentRow(0)
    dialog.outline.blockSignals(False)
    _refill_library_list(dialog)


def _search_library(dialog, text: str) -> None:
    dialog._library_query = text
    _refill_library_list(dialog)


def _show_library_folder(dialog, folder: str) -> None:
    dialog._library_folder = folder
    if hasattr(dialog, "library_search"):
        dialog.library_search.blockSignals(True)
        dialog.library_search.clear()
        dialog.library_search.blockSignals(False)
    dialog._library_query = ""
    _refill_library_list(dialog)


def _library_matches(dialog) -> list[dict]:
    catalog = getattr(dialog, "_catalog", None) or []
    query = (getattr(dialog, "_library_query", "") or "").strip().casefold()
    if len(query) >= 2:
        found = []
        for group in catalog:
            for node in group["nodes"]:
                if query in node["label"].casefold() or query in node["internal"].casefold():
                    found.append(node)
                    if len(found) >= 250:
                        return found
        return found
    folder = getattr(dialog, "_library_folder", "")
    for group in catalog:
        if group["folder"] == folder:
            return group["nodes"]
    return []


def _refill_library_list(dialog) -> None:
    widgets = dialog._widgets
    core = dialog._core
    listing = dialog.library_list
    listing.clear()
    rows = _library_matches(dialog)
    query = (getattr(dialog, "_library_query", "") or "").strip()
    if len(query) >= 2:
        dialog.library_count.setText(f"{len(rows)} matches")
    else:
        label = next((group["label"] for group in dialog._catalog if group["folder"] == dialog._library_folder), "")
        dialog.library_count.setText(f"{label}  ·  {len(rows)} pages" if label else "")
    for node in rows:
        item = widgets.QListWidgetItem(node["label"])
        item.setData(core.Qt.UserRole, node)
        listing.addItem(item)


def _open_catalog_node(dialog, item) -> None:
    node = item.data(dialog._core.Qt.UserRole)
    if not isinstance(node, dict):
        return
    hfs = getattr(dialog, "_hfs", "") or ""
    try:
        help_file = installed_help(node["category"], node["internal"], hfs)
    except (FileNotFoundError, OSError):
        return
    scene = {
        "type_label": node["label"],
        "category": node["category"],
        "path": "",
        "hfs": hfs,
        "includes": list(help_file.includes),
        "error": "",
        "parm_label": "",
        "values": {},
        "ranges": {},
        "tooltips": {},
        "inputs": [],
        "outputs": [],
    }
    study = build_study(help_file.sections, scene, "")
    study["library_page"] = True
    study["note"] = "No node is selected. Select one in the network and this window follows it."
    dialog.present(study, raise_window=False)


def _on_outline(dialog, row: int) -> None:
    if row < 0:
        return
    item = dialog.outline.item(row)
    if item is None:
        return
    key = item.data(dialog._core.Qt.UserRole)
    if isinstance(key, str) and key.startswith("cat:"):
        _show_library_folder(dialog, key.split(":", 1)[1])
        return
    _activate(dialog, key)


def _activate(dialog, key: str) -> None:
    if not key:
        return
    if key.startswith("tab:"):
        if dialog.tabs is not None:
            dialog.tabs.setCurrentIndex(int(key.split(":", 1)[1]))
        target = dialog.tabs
    else:
        index = dialog._parm_folder.get(key)
        if dialog.tabs is not None and isinstance(index, int):
            dialog.tabs.setCurrentIndex(index)
        target = dialog._anchors.get(key)
    if target is not None:
        dialog.scroll.ensureWidgetVisible(target, 0, 28)


def _parameter(widgets, row: dict, depth: int = 0):
    card = widgets.QFrame()
    card.setFrameShape(widgets.QFrame.NoFrame)
    card.setObjectName("selected" if row.get("selected") else "parm")
    layout = widgets.QVBoxLayout(card)
    layout.setContentsMargins(10 + depth * 16, 7, 10, 7)
    layout.setSpacing(3)
    title = widgets.QLabel(row["name"])
    title.setObjectName("parmName")
    layout.addWidget(title)
    if row.get("meaning"):
        meaning = widgets.QLabel(row["meaning"])
        meaning.setObjectName("meaning")
        meaning.setWordWrap(True)
        layout.addWidget(meaning)
    if row.get("range"):
        span = widgets.QLabel(row["range"])
        span.setObjectName("range")
        span.setWordWrap(True)
        layout.addWidget(span)
    if row.get("current") and not any(option.get("current") for option in row.get("options") or []):
        now = widgets.QLabel(f"Now: {row['current']}")
        now.setObjectName("now")
        now.setWordWrap(True)
        layout.addWidget(now)
    for option in row.get("options") or []:
        marker = "Now" if option.get("current") else "•"
        text = f"{marker}  {option['name']}"
        if option.get("meaning"):
            text = f"{text}  —  {option['meaning']}"
        line = widgets.QLabel(text)
        line.setObjectName("optionNow" if option.get("current") else "option")
        line.setWordWrap(True)
        layout.addWidget(line)
    return card


def _load_pixmap(dialog, hfs: str, path: str):
    gui = dialog._gui
    core = dialog._core
    data = image_bytes(hfs, path)
    if not data:
        return None
    image = gui.QImage.fromData(data)
    if image.isNull():
        return None
    pixmap = gui.QPixmap.fromImage(image)
    height = max(96, int(180 * getattr(dialog, "_zoom", 1.0)))
    try:
        return pixmap.scaledToHeight(height, core.Qt.SmoothTransformation)
    except Exception:
        return pixmap.scaledToHeight(height)


def _figure_pixmaps(dialog, hfs: str, figure: dict):
    widgets = dialog._widgets
    box = widgets.QWidget()
    layout = widgets.QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    if figure.get("label"):
        label = widgets.QLabel(figure["label"])
        label.setObjectName("figureLabel")
        layout.addWidget(label)
    row = widgets.QHBoxLayout()
    shown = False
    for path in figure.get("images") or []:
        pixmap = _load_pixmap(dialog, hfs, path)
        if pixmap is None:
            continue
        shown = True
        pic = widgets.QLabel()
        pic.setProperty("wikiPath", path)
        pic.setProperty("hfs", hfs)
        pic.setPixmap(pixmap)
        row.addWidget(pic)
    row.addStretch(1)
    if shown:
        layout.addLayout(row)
    return box


def _icon_label(dialog, name: str):
    if not name:
        return None
    try:
        import hou

        icon = hou.qt.Icon(name, 28, 28)
        pixmap = icon.pixmap(28, 28)
    except Exception:
        return None
    if pixmap.isNull():
        return None
    label = dialog._widgets.QLabel()
    label.setPixmap(pixmap)
    label.setFixedSize(32, 32)
    return label


def _ends_box(widgets, title: str, rows: list[dict], empty: str):
    box = widgets.QGroupBox(title)
    box.setFlat(True)
    layout = widgets.QVBoxLayout(box)
    if not rows:
        label = widgets.QLabel(empty)
        label.setWordWrap(True)
        layout.addWidget(label)
        return box
    for row in rows:
        state = row["state"]
        text = row["label"] if not state else f"{row['label']}: {state}"
        label = widgets.QLabel(text)
        label.setObjectName("wire")
        label.setWordWrap(True)
        layout.addWidget(label)
        if row.get("meaning"):
            meaning = widgets.QLabel(row["meaning"])
            meaning.setObjectName("meaning")
            meaning.setWordWrap(True)
            layout.addWidget(meaning)
    return box


def _service_banner(widgets, service: dict):
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    frame = widgets.QFrame()
    frame.setObjectName("service")
    frame.setProperty("state", service.get("state") or "working")
    frame.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    column = widgets.QVBoxLayout(frame)
    column.setContentsMargins(10, 8, 10, 8)
    column.setSpacing(2)
    title = widgets.QLabel(service.get("title") or "")
    title.setObjectName("serviceTitle")
    column.addWidget(title)
    detail = service.get("detail") or ""
    if detail:
        body = widgets.QLabel(detail)
        body.setObjectName("serviceDetail")
        body.setWordWrap(True)
        column.addWidget(body)
    return frame


def _callout(widgets, text: str, name: str):
    label = widgets.QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _help_link(dialog, label: str, path: str):
    button = dialog._widgets.QPushButton(label)
    button.setObjectName("helpLink")
    button.setCursor(dialog._gui.QCursor(dialog._core.Qt.PointingHandCursor))
    button.setFlat(True)
    button.clicked.connect(lambda _checked=False, path=path, dialog=dialog: _open_help(dialog, path))
    return button


def _open_help(dialog, path: str) -> None:
    """Open the help page as a new tab in the help browser, not a new window."""
    hou = getattr(dialog, "_hou", None)
    ui = getattr(hou, "ui", None) if hou is not None else None
    if hou is None or ui is None or not path:
        return
    try:
        desktop = ui.curDesktop()
        browsers = [tab for tab in desktop.paneTabs() if tab.type() == hou.paneTabType.HelpBrowser and not tab.isFloating()]
        if browsers:
            tab = browsers[-1].pane().createTab(hou.paneTabType.HelpBrowser)
            tab.displayHelpPath(path)
            tab.setIsCurrentTab()
            return
        desktop.displayHelpPath(path)
    except Exception:
        return


def _section_label(widgets, text: str):
    label = widgets.QLabel(text)
    label.setObjectName("section")
    return label


def _selected_name(study: dict | None) -> str:
    if not study:
        return ""
    for row in study.get("parameters") or []:
        if row.get("selected"):
            return row["name"]
    return ""


def _step_zoom(dialog, delta: int) -> None:
    current = int(round(dialog._zoom * 100))
    if delta > 0:
        target = (current // 10) * 10 + 10
    else:
        base = (current // 10) * 10
        target = base if current != base else current - 10
    _set_zoom(dialog, target, snap=True)


def _set_zoom(dialog, percent: int, snap: bool) -> None:
    percent = int(percent)
    if snap:
        percent = int(round(percent / 10.0) * 10)
    percent = max(70, min(180, percent))
    if abs(dialog._zoom - (percent / 100)) < 0.001 and int(round(dialog._zoom * 100)) == percent:
        dialog.zoom_label.setText(f"{percent}%")
        return
    dialog._zoom = percent / 100
    dialog.zoom_slider.blockSignals(True)
    dialog.zoom_slider.setValue(percent)
    dialog.zoom_slider.blockSignals(False)
    _restyle(dialog)


def _toggle_nav(dialog, open_nav: bool) -> None:
    sizes = dialog.splitter.sizes()
    total = max(sum(sizes), 800)
    if open_nav:
        width = dialog._nav_width or 210
        dialog.splitter.setSizes([width, max(200, total - width)])
        return
    if sizes[0] > 24:
        dialog._nav_width = sizes[0]
    dialog.splitter.setSizes([0, total])


def _toggle_theme(dialog) -> None:
    dialog._theme = "light" if dialog._theme == "dark" else "dark"
    _restyle(dialog)


def _restyle(dialog) -> None:
    bar = dialog.scroll.verticalScrollBar()
    position = bar.value()
    percent = int(round(dialog._zoom * 100))
    dialog.setStyleSheet(_style(dialog._theme, dialog._zoom))
    dialog.zoom_label.setText(f"{percent}%")
    if hasattr(dialog, "zoom_slider"):
        dialog.zoom_slider.blockSignals(True)
        dialog.zoom_slider.setValue(percent)
        dialog.zoom_slider.blockSignals(False)
    dialog.theme_button.setText("Dark" if dialog._theme == "light" else "Light")
    _rescale_figures(dialog)
    bar.setValue(position)


def _rescale_figures(dialog) -> None:
    widgets = dialog._widgets
    for pic in dialog.findChildren(widgets.QLabel):
        path = pic.property("wikiPath")
        hfs = pic.property("hfs")
        if not path or not hfs:
            continue
        pixmap = _load_pixmap(dialog, str(hfs), str(path))
        if pixmap is not None:
            pic.setPixmap(pixmap)


def _empty_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.hide()
            child.setParent(None)
            child.deleteLater()
        nested = item.layout()
        if nested is not None:
            _empty_layout(nested)


def _clear_layout(layout) -> None:
    _empty_layout(layout)


def _fit(dialog) -> None:
    screen = dialog.screen()
    if screen is None:
        dialog.resize(960, 720)
        return
    area = screen.availableGeometry()
    dialog.resize(min(980, int(area.width() * 0.52)), min(820, int(area.height() * 0.78)))


def _follow(hou, window, refresh) -> None:
    global _CALLBACK
    if refresh is None or not hasattr(hou.ui, "addEventLoopCallback"):
        return
    if _CALLBACK is not None:
        return

    def tick() -> None:
        if _WINDOW is None:
            _stop_follow(hou)
            return
        try:
            payload = refresh()
        except Exception:
            return
        if not payload:
            return
        sections, scene, focus, extra = payload
        study = build_study(sections, scene, focus)
        if scene.get("service"):
            study["service"] = scene["service"]
        if extra:
            study["note"] = f"{extra} {study['note']}".strip()
        window.present(study, raise_window=False)

    _CALLBACK = tick
    try:
        hou.ui.addEventLoopCallback(tick)
    except Exception:
        _CALLBACK = None


def _stop_follow(hou) -> None:
    global _CALLBACK
    callback = _CALLBACK
    _CALLBACK = None
    if callback is None:
        return
    try:
        hou.ui.removeEventLoopCallback(callback)
    except Exception:
        pass


def _plain_panel(sections, scene: dict, focus_heading: str, extra_note: str) -> None:
    import hou

    study = build_study(sections, scene, focus_heading)
    service = scene.get("service") or {}
    lines = [
        service.get("title") or "",
        service.get("detail") or "",
        study.get("where") or "",
        study.get("summary") or "",
        study.get("error") or "",
        extra_note,
        study.get("note") or "",
        "The parameters of this node are listed below. A guide to adjusting their values is included.",
    ]
    for row in study.get("parameters") or []:
        lines.append(row["name"])
        if row.get("meaning"):
            lines.append(row["meaning"])
        if row.get("range"):
            lines.append(row["range"])
        for option in row.get("options") or []:
            lines.append(f"{option['name']}: {option['meaning']}")
    text = "\n\n".join(part for part in lines if part)
    hou.ui.displayMessage(text, title=study.get("type_label") or "Houdini wizard")


def _px(zoom: float, size: int) -> int:
    return max(11, int(round(size * zoom)))


def _style(theme: str, zoom: float) -> str:
    if theme == "light":
        bg, fg, muted, accent, card, line, nav, select, call = (
            "#f6f1e8",
            "#2c261f",
            "#6d6256",
            "#8a5a22",
            "#fffdf8",
            "#e4d9cb",
            "#efe7db",
            "#e7d7c0",
            "#f3e4d4",
        )
        link = "#1565c0"
        scroll = "#5c5146"
        work_bg, work_fg = "#e6e4f2", "#34315f"
        ok_bg, ok_fg = "#dcecde", "#1d5c32"
        back_bg, back_fg = "#d9e6f5", "#1a4578"
        here_bg, here_fg = "#efe6d8", "#5c4a32"
        off_bg, off_fg = "#f3e6cf", "#7a5410"
        bad_bg, bad_fg = "#f6dcd6", "#8a2e24"
    else:
        bg, fg, muted, accent, card, line, nav, select, call = (
            "#241f1b",
            "#f4efe6",
            "#b7aa96",
            "#d7a15a",
            "#1b1714",
            "#3a332c",
            "#1b1714",
            "#3c342c",
            "#3a2a22",
        )
        link = "#8eb7ff"
        scroll = "#efe6d6"
        work_bg, work_fg = "#2a2838", "#e4def8"
        ok_bg, ok_fg = "#1c3326", "#c8efd4"
        back_bg, back_fg = "#1c2c40", "#d4e6fa"
        here_bg, here_fg = "#2c2824", "#e7dcc8"
        off_bg, off_fg = "#3a3224", "#f3e0b8"
        bad_bg, bad_fg = "#3c2222", "#f6d0c8"
    body = _px(zoom, 14)
    return f"""
QDialog {{ background: {bg}; color: {fg}; }}
QScrollArea {{ background: {bg}; border: none; }}
QWidget#page {{ background: {bg}; }}
QLabel {{ color: {fg}; font-size: {body}px; }}
QLabel#where {{ color: {accent}; font-size: {_px(zoom, 14)}px; }}
QLabel#title {{ font-size: {_px(zoom, 22)}px; font-weight: 600; }}
QLabel#summary {{ color: {fg}; font-size: {_px(zoom, 17)}px; }}
QLabel#path, QLabel#nextWhy {{ color: {muted}; font-size: {_px(zoom, 14)}px; }}
QLabel#helpLink {{ font-size: {_px(zoom, 15)}px; font-weight: 600; }}
QLabel#helpLink a {{ color: {link}; text-decoration: underline; }}
QLabel#intro {{ color: {muted}; font-size: {_px(zoom, 15)}px; }}
QLabel#section {{ color: {accent}; font-size: {_px(zoom, 15)}px; font-weight: 600; padding-top: 6px; }}
QLabel#folderHead {{ color: {accent}; font-size: {_px(zoom, 14)}px; font-weight: 600; }}
QLabel#parmName {{ font-size: {_px(zoom, 16)}px; font-weight: 600; }}
QLabel#meaning, QLabel#step {{ color: {fg}; font-size: {_px(zoom, 15)}px; }}
QLabel#range {{ color: {accent}; font-size: {_px(zoom, 14)}px; }}
QLabel#now, QLabel#optionNow {{ color: {accent}; }}
QLabel#option {{ color: {muted}; }}
QLabel#nextNames {{ color: {fg}; font-weight: 600; font-size: {_px(zoom, 15)}px; }}
QLabel#figureLabel {{ color: {muted}; font-size: {_px(zoom, 14)}px; }}
QLabel#zoom {{ color: {fg}; font-size: 13px; padding: 0 6px; }}
QLabel#error, QLabel#callout, QLabel#cache {{
    background: {call}; color: {fg}; padding: 8px 10px; border-radius: 6px;
}}
QFrame#service {{ border-radius: 6px; }}
QFrame#service QLabel {{ background: transparent; }}
QLabel#serviceTitle {{ font-weight: 700; font-size: {_px(zoom, 14)}px; }}
QLabel#serviceDetail {{ font-weight: 400; font-size: {_px(zoom, 14)}px; }}
QFrame#service[state="working"] {{ background: {work_bg}; }}
QFrame#service[state="working"] QLabel {{ color: {work_fg}; }}
QFrame#service[state="online"] {{ background: {ok_bg}; }}
QFrame#service[state="online"] QLabel {{ color: {ok_fg}; }}
QFrame#service[state="restored"] {{ background: {back_bg}; }}
QFrame#service[state="restored"] QLabel {{ color: {back_fg}; }}
QFrame#service[state="local"] {{ background: {here_bg}; }}
QFrame#service[state="local"] QLabel {{ color: {here_fg}; }}
QFrame#service[state="offline"] {{ background: {off_bg}; }}
QFrame#service[state="offline"] QLabel {{ color: {off_fg}; }}
QFrame#service[state="error"] {{ background: {bad_bg}; }}
QFrame#service[state="error"] QLabel {{ color: {bad_fg}; }}
QListWidget#outline {{ background: {nav}; color: {fg}; border: none; font-size: {body}px; }}
QListWidget#libraryList {{ background: {bg}; color: {fg}; border: none; font-size: {body}px; }}
QListWidget#libraryList::item {{ padding: 4px 2px; }}
QListWidget#libraryList::item:selected {{ background: {select}; color: {fg}; }}
QLineEdit#librarySearch {{
    background: {card}; color: {fg}; border: 1px solid {line}; border-radius: 4px;
    padding: 6px 8px; font-size: {body}px;
}}
QListWidget#outline::item {{ padding: 3px 8px; }}
QListWidget#outline::item:selected {{ background: {select}; color: {fg}; }}
QFrame#parm, QFrame#selected {{ background: {card}; border: 1px solid {line}; border-radius: 4px; }}
QFrame#selected {{ border: 1px solid {accent}; }}
QGroupBox {{
    border: 1px solid {line}; border-radius: 4px; margin-top: 12px; padding: 8px;
    color: {muted}; font-size: {body}px; background: transparent;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
QTabWidget::pane {{ border: 1px solid {line}; background: {bg}; top: -1px; }}
QTabBar::tab {{
    background: {bg}; color: {muted}; padding: 6px 12px; border: none; font-size: {body}px;
}}
QTabBar::tab:selected {{ color: {fg}; border-bottom: 2px solid {accent}; }}
QPushButton {{
    background: {select}; color: {fg}; border: none; border-radius: 6px;
    padding: 4px 10px; font-size: 13px;
}}
QPushButton#zoomOut {{ font-size: 12px; padding: 2px 8px; }}
QPushButton#zoomIn {{ font-size: 18px; font-weight: 700; padding: 1px 10px; }}
QPushButton:hover, QPushButton:checked {{ background: {accent}; color: {bg}; }}
QTabBar::tab:hover {{ background: {select}; color: {fg}; }}
QListWidget#outline::item:hover {{ background: {select}; color: {fg}; }}
QSplitter::handle {{ background: {line}; }}
QSplitter::handle:hover {{ background: {accent}; }}
QSlider::groove:horizontal {{ height: 4px; background: {line}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; background: {accent}; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {fg}; }}
QPushButton#helpLink {{
    background: transparent; color: {link}; border: none; border-radius: 0;
    padding: 1px 0; font-size: {_px(zoom, 15)}px; font-weight: 600; text-align: left;
}}
QPushButton#helpLink:hover {{ background: transparent; color: {link}; text-decoration: underline; }}
QScrollArea#guideScroll QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollArea#guideScroll QScrollBar::handle:vertical {{
    background: {scroll}; border-radius: 6px; min-height: 28px; margin: 2px;
}}
QScrollArea#guideScroll QScrollBar::add-line:vertical,
QScrollArea#guideScroll QScrollBar::sub-line:vertical {{ height: 0; background: transparent; }}
QScrollArea#guideScroll QScrollBar::add-page:vertical,
QScrollArea#guideScroll QScrollBar::sub-page:vertical {{ background: transparent; }}
"""
