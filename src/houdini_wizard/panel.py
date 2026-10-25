"""A help panel for the node that is open, not a script message box."""

from __future__ import annotations

from houdini_wizard.context import build_study
from houdini_wizard.help_file import Section


def show_panel(sections: tuple[Section, ...] | list[Section], scene: dict, focus_heading: str, extra_note: str = "") -> None:
    try:
        _qt_panel(sections, scene, focus_heading, extra_note)
    except Exception:
        _plain_panel(sections, scene, focus_heading, extra_note)


def _qt_panel(sections, scene: dict, focus_heading: str, extra_note: str) -> None:
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    import hou

    study = build_study(sections, scene, focus_heading)
    if extra_note:
        study["note"] = f"{extra_note}\n\n{study['note']}".strip()

    dialog = QtWidgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowFlags(QtCore.Qt.Window)
    dialog.setWindowTitle(study["type_label"])
    dialog.resize(760, 680)
    dialog.setStyleSheet(_STYLE)

    root = QtWidgets.QVBoxLayout(dialog)
    root.setContentsMargins(28, 24, 28, 20)
    root.setSpacing(12)

    where = QtWidgets.QLabel(study["where"])
    where.setObjectName("where")
    where.setWordWrap(True)
    root.addWidget(where)

    title = QtWidgets.QLabel(study["type_label"])
    title.setObjectName("title")
    root.addWidget(title)

    path = QtWidgets.QLabel(study["path"])
    path.setObjectName("path")
    root.addWidget(path)

    if study["error"]:
        error = QtWidgets.QLabel(study["error"])
        error.setObjectName("error")
        error.setWordWrap(True)
        root.addWidget(error)

    note = QtWidgets.QLabel(study["note"])
    note.setObjectName("note")
    note.setWordWrap(True)
    root.addWidget(note)

    columns = QtWidgets.QHBoxLayout()
    columns.addWidget(_group(QtWidgets, "Wired in", study["wires_in"] or ["This node has no inputs."]))
    columns.addWidget(_group(QtWidgets, "Wired onward", study["wires_out"] or ["This node has no outputs."]))
    root.addLayout(columns)

    if study["folders"]:
        tabs = QtWidgets.QLabel("Parameter window: " + "  ·  ".join(study["folders"]))
        tabs.setObjectName("tabs")
        tabs.setWordWrap(True)
        root.addWidget(tabs)

    if study["related"]:
        related = QtWidgets.QLabel("Often used with: " + ", ".join(study["related"]))
        related.setObjectName("related")
        related.setWordWrap(True)
        root.addWidget(related)

    quote_title = QtWidgets.QLabel(study["focus_heading"] or "Help")
    quote_title.setObjectName("quoteTitle")
    root.addWidget(quote_title)

    quote = QtWidgets.QTextEdit()
    quote.setReadOnly(True)
    quote.setPlainText(study["focus_body"] or "This heading has no text in the installed file.")
    root.addWidget(quote, 1)

    picker = QtWidgets.QComboBox()
    picker.addItems(study["headings"])
    if study["focus_heading"] in study["headings"]:
        picker.setCurrentText(study["focus_heading"])

    def swap() -> None:
        chosen = picker.currentText()
        next_study = build_study(sections, scene, chosen)
        quote_title.setText(next_study["focus_heading"])
        quote.setPlainText(next_study["focus_body"] or "This heading has no text in the installed file.")
        note.setText(next_study["note"])

    picker.currentTextChanged.connect(swap)
    root.addWidget(picker)

    close = QtWidgets.QPushButton("Back to the node")
    close.clicked.connect(dialog.accept)
    root.addWidget(close)
    dialog.exec()


def _group(qt, title: str, lines: list[str]):
    box = qt.QGroupBox(title)
    layout = qt.QVBoxLayout(box)
    label = qt.QLabel("\n\n".join(lines))
    label.setWordWrap(True)
    layout.addWidget(label)
    return box


def _plain_panel(sections, scene: dict, focus_heading: str, extra_note: str) -> None:
    import hou

    study = build_study(sections, scene, focus_heading)
    text = "\n\n".join(
        part
        for part in (
            study["where"],
            study["error"],
            extra_note,
            study["note"],
            "\n".join(study["wires_in"]),
            study["focus_body"],
        )
        if part
    )
    hou.ui.displayMessage(text, title=study["type_label"])


_STYLE = """
QDialog { background: #241f1b; color: #f4efe6; }
QLabel { color: #f4efe6; font-size: 14px; }
QLabel#where { color: #d7a15a; font-size: 13px; }
QLabel#title { font-size: 28px; font-weight: 600; }
QLabel#path { color: #b7aa96; }
QLabel#error { background: #3a2a22; color: #f4efe6; padding: 10px 12px; border-radius: 8px; }
QLabel#note { font-size: 15px; }
QLabel#tabs, QLabel#related, QLabel#quoteTitle { color: #d7c4a8; }
QGroupBox { border: 1px solid #3c342c; border-radius: 8px; margin-top: 12px; padding: 12px; color: #d7c4a8; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTextEdit { background: #1b1714; color: #f4efe6; border: none; border-radius: 8px; padding: 12px; font-size: 14px; }
QComboBox, QPushButton { background: #3c342c; color: #f4efe6; border: none; border-radius: 8px; padding: 8px 12px; }
QPushButton:hover, QComboBox:hover { background: #4a4036; }
"""
