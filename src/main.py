"""
Project Tree Generator Pro
A professional tool to generate project tree structures and optionally include file contents.
Supports English and Persian languages with Vazirmatn font.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Q_ARG,
    QCoreApplication,
    QDir,
    QEvent,
    QMetaObject,
    QMutex,
    QMutexLocker,
    QObject,
    QRecursiveMutex,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    QTranslator,
    Signal,
    Slot,
)
from PySide6.QtGui import QActionGroup, QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# ======================================================================
# Application Constants
# ======================================================================
APP_VERSION = "1.0.0"
GITHUB_REPO = "amrezzio/Project-Tree-Generator-Pro"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


# ----------------------------------------------------------------------
# Logging Setup (with Size Limit & Rotation)
# ----------------------------------------------------------------------
def _get_log_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "app.log")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    _log_handler = RotatingFileHandler(
        _get_log_path(), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _log_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")
    )
    logger.addHandler(_log_handler)


# ----------------------------------------------------------------------
# Path Helpers
# ----------------------------------------------------------------------
def _bundle_path() -> str:
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore
    return os.path.dirname(os.path.abspath(__file__))


def _writable_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _settings_path() -> str:
    return os.path.join(_writable_path(), "settings.ini")


def _translations_dir() -> str:
    return os.path.join(_bundle_path(), "translations")


def _fonts_dir() -> str:
    return os.path.join(_bundle_path(), "fonts")


_app_settings = QSettings(_settings_path(), QSettings.IniFormat)


# ----------------------------------------------------------------------
# Smart Sensitive Path Detection
# ----------------------------------------------------------------------
SENSITIVE_NAMES = {
    ".git",
    ".svn",
    ".hg",
    ".vscode",
    ".idea",
    ".env",
    ".env.local",
    "__pycache__",
    "venv",
    "env",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "Release",
    ".pytest_cache",
    ".ruff_cache",
    "target",
}


def _is_sensitive_path(path: str) -> bool:
    path_lower = path.lower().replace("\\", "/")
    for name in SENSITIVE_NAMES:
        if (
            f"/{name}/" in path_lower
            or path_lower.endswith(f"/{name}")
            or path_lower == name
            or path_lower.startswith(f"{name}/")
        ):
            return True
    return False


# ----------------------------------------------------------------------
# Binary File Detection
# ----------------------------------------------------------------------
def is_binary_file(file_path: str) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(65536)
            if b"\x00" in chunk:
                return True
            chunk.decode("utf-8")
            return False
    except UnicodeDecodeError:
        return True
    except Exception as e:
        logger.error(f"Error checking binary status of {file_path}: {e}")
        return True


# ======================================================================
# Update Worker (Background Thread)
# ======================================================================
class UpdateWorker(QThread):
    update_available = Signal(str, str)
    no_update = Signal()
    download_progress = Signal(int)
    download_finished = Signal(str)
    error = Signal(str)

    def __init__(self, action: str, download_url: str = ""):
        super().__init__()
        self.action = action
        self.download_url = download_url

    def run(self) -> None:
        if self.action == "check":
            try:
                req = urllib.request.Request(
                    GITHUB_API_URL, headers={"User-Agent": "ProjectTreeGenerator"}
                )
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode())
                    latest_version = data.get("tag_name", "v0.0.0").lstrip("v")
                    assets = data.get("assets", [])

                    download_url = ""
                    for asset in assets:
                        if asset["name"].endswith(".exe"):
                            download_url = asset["browser_download_url"]
                            break

                    if latest_version > APP_VERSION and download_url:
                        self.update_available.emit(latest_version, download_url)
                    else:
                        self.no_update.emit()
            except urllib.error.HTTPError as e:
                logger.error(f"Update check HTTP error: {e.code} - {e.reason}")
                self.error.emit(f"HTTP {e.code}")
            except Exception as e:
                logger.error(f"Update check failed: {e}")
                self.error.emit(str(e))

        elif self.action == "download":
            try:
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, "ProjectTreeGeneratorPro_Setup.exe")

                req = urllib.request.Request(
                    self.download_url, headers={"User-Agent": "ProjectTreeGenerator"}
                )
                with urllib.request.urlopen(req) as response:
                    total_size = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunk_size = 8192

                    with open(file_path, "wb") as f:
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                self.download_progress.emit(progress)

                self.download_finished.emit(file_path)
            except Exception as e:
                logger.error(f"Download failed: {e}")
                self.error.emit(str(e))


# ======================================================================
# About & Update Dialog
# ======================================================================
class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("About Project Tree Generator Pro"))
        self.resize(450, 300)
        self.setFixedSize(450, 300)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_label = QLabel("<h2>Project Tree Generator Pro</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(self.tr("Version: {}").format(APP_VERSION))
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        desc_label = QLabel(
            self.tr(
                "A professional tool to generate project tree structures and optionally include file contents. Perfect for sharing with AI or teammates."
            )
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        github_label = QLabel(self.tr("GitHub Repository:"))
        layout.addWidget(github_label)

        link_browser = QTextBrowser()
        link_browser.setOpenExternalLinks(True)
        link_browser.setHtml(
            '<a href="https://github.com/amrezzio/Project-Tree-Generator-Pro">https://github.com/amrezzio/Project-Tree-Generator-Pro</a>'
        )
        link_browser.setMaximumHeight(30)
        link_browser.setStyleSheet("QTextBrowser { border: none; background: transparent; }")
        layout.addWidget(link_browser)

        layout.addStretch()

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.update_btn = QPushButton(self.tr("Check for Updates"))
        self.update_btn.clicked.connect(self.handle_update_action)
        layout.addWidget(self.update_btn)

        self.worker: UpdateWorker | None = None

    def handle_update_action(self) -> None:
        if self.update_btn.text() == self.tr("Check for Updates"):
            self.update_btn.setText(self.tr("Checking..."))
            self.update_btn.setEnabled(False)
            self.status_label.setText("")

            self.worker = UpdateWorker("check")
            self.worker.update_available.connect(self.on_update_available)
            self.worker.no_update.connect(self.on_no_update)
            self.worker.error.connect(self.on_error)
            self.worker.start()

        elif self.update_btn.text() == self.tr("Download Update"):
            self.update_btn.setText(self.tr("Downloading..."))
            self.update_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.status_label.setText("")

            self.worker = UpdateWorker("download", self._download_url)
            self.worker.download_progress.connect(self.progress_bar.setValue)
            self.worker.download_finished.connect(self.on_download_finished)
            self.worker.error.connect(self.on_error)
            self.worker.start()

    def on_update_available(self, version: str, url: str) -> None:
        self._download_url = url
        self.update_btn.setText(self.tr("Download Update"))
        self.update_btn.setEnabled(True)
        self.status_label.setText(self.tr("Update available: Version {}").format(version))
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

    def on_no_update(self) -> None:
        self.update_btn.setText(self.tr("Check for Updates"))
        self.update_btn.setEnabled(True)
        self.status_label.setText(self.tr("You are using the latest version."))
        self.status_label.setStyleSheet("color: gray;")

    def on_download_finished(self, file_path: str) -> None:
        self.status_label.setText(self.tr("Download complete. Installing..."))
        self.status_label.setStyleSheet("color: blue;")

        try:
            subprocess.Popen([file_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
            sys.exit(0)
        except Exception as e:
            self.on_error(str(e))

    def on_error(self, error_msg: str) -> None:
        self.update_btn.setText(self.tr("Check for Updates"))
        self.update_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if "HTTP 404" in error_msg:
            self.status_label.setText(self.tr("No releases found yet."))
        elif "HTTP 403" in error_msg:
            self.status_label.setText(self.tr("GitHub API rate limit exceeded. Try again later."))
        else:
            self.status_label.setText(
                self.tr("Error checking for updates. Check your internet connection.")
            )
        self.status_label.setStyleSheet("color: red;")
        logger.error(f"Update error: {error_msg}")


# ======================================================================
# Exclude Dirs Dialog
# ======================================================================
class ExcludeDirsDialog(QDialog):
    def __init__(self, current_excludes: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit Excluded Directories"))
        self.resize(854, 480)
        if parent:
            parent_frame = parent.frameGeometry()
            self.move(
                parent_frame.x() + (parent_frame.width() - self.width()) // 2,
                parent_frame.y() + (parent_frame.height() - self.height()) // 2,
            )
        self.setMinimumSize(854, 480)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.addItems(sorted(list(current_excludes)))
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(QLabel(self.tr("Directories to exclude:")))
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton(self.tr("Add"))
        self.remove_btn = QPushButton(self.tr("Remove Selected"))
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        layout.addLayout(btn_layout)

        self.new_dir_input = QLineEdit()
        self.new_dir_input.setPlaceholderText(self.tr("Enter directory name..."))
        layout.addWidget(self.new_dir_input)

        dlg_btns = QHBoxLayout()
        ok_btn = QPushButton(self.tr("OK"))
        cancel_btn = QPushButton(self.tr("Cancel"))
        dlg_btns.addStretch()
        dlg_btns.addWidget(ok_btn)
        dlg_btns.addWidget(cancel_btn)
        layout.addLayout(dlg_btns)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self.add_btn.clicked.connect(self.add_exclude)
        self.remove_btn.clicked.connect(self.remove_exclude)

    def add_exclude(self) -> None:
        name = self.new_dir_input.text().strip()
        if name and not self.list_widget.findItems(name, Qt.MatchExactly):
            self.list_widget.addItem(name)
            self.new_dir_input.clear()

    def remove_exclude(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_excludes(self) -> set[str]:
        return {self.list_widget.item(i).text() for i in range(self.list_widget.count())}


# ======================================================================
# Background Worker for Descendant State Updates & Bulk Content
# ======================================================================
class DescendantUpdateWorker(QObject):
    update_finished = Signal(list)
    content_update_finished = Signal(list)

    def __init__(self, model: "CheckableFileSystemModel") -> None:
        super().__init__()
        self.model = model
        self.queue: deque = deque()
        self.mutex = QMutex()
        self.processing = False
        self.content_canceled = False

    @Slot(str, int)
    def enqueue(self, target_path: str, new_state: int) -> None:
        with QMutexLocker(self.mutex):
            self.queue.append((target_path, new_state))
        if not self.processing:
            self.processing = True
            QMetaObject.invokeMethod(self, "process_next", Qt.QueuedConnection)

    @Slot()
    def process_next(self) -> None:
        with QMutexLocker(self.mutex):
            if not self.queue:
                self.processing = False
                return
            target_path, new_state = self.queue.popleft()

        updates = {}
        try:
            for root, dirs, files in os.walk(target_path):
                for d in dirs:
                    updates[(Path(root) / d).as_posix()] = new_state
                for f in files:
                    updates[(Path(root) / f).as_posix()] = new_state
        except Exception as e:
            logger.error(f"Error walking {target_path}: {e}")

        with QMutexLocker(self.model.mutex):
            self.model.check_states.update(updates)

        self.update_finished.emit(list(updates.keys()))
        QMetaObject.invokeMethod(self, "process_next", Qt.QueuedConnection)

    @Slot(str, int)
    def set_all_content_states(self, root_path: str, new_state: int) -> None:
        self.content_canceled = False
        updates = {}
        try:
            for r, dirs, files in os.walk(root_path):
                if self.content_canceled:
                    return
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in self.model.exclude_dirs
                    and not _is_sensitive_path((Path(r) / d).as_posix())
                ]
                for f in files:
                    if self.content_canceled:
                        return
                    full = (Path(r) / f).as_posix()
                    if (
                        self.model.check_states.get(full, 0 if _is_sensitive_path(full) else 2) == 2
                        and not _is_sensitive_path(full)
                        and not is_binary_file(full)
                    ):
                        updates[full] = new_state
        except Exception as e:
            logger.error(f"Error in set_all_content_states: {e}")

        if not self.content_canceled:
            with QMutexLocker(self.model.mutex):
                self.model.content_check_states.update(updates)
            self.content_update_finished.emit(list(updates.keys()))


# ======================================================================
# Custom File System Model with Robust, Instant Checkbox Logic
# ======================================================================
class CheckableFileSystemModel(QFileSystemModel):
    content_state_toggled = Signal(str, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.check_states: dict[str, int] = {}
        self.content_check_states: dict[str, int] = {}
        self.binary_files: set[str] = set()
        self.exclude_dirs: set[str] = set()

        self.mutex = QRecursiveMutex()

        self.desc_thread = QThread()
        self.desc_worker = DescendantUpdateWorker(self)
        self.desc_worker.moveToThread(self.desc_thread)
        self.desc_worker.update_finished.connect(
            self._on_descendant_update_finished, Qt.QueuedConnection
        )
        self.desc_worker.content_update_finished.connect(
            self._on_content_update_finished, Qt.QueuedConnection
        )
        self.desc_thread.start()

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return self.tr("Name")
            elif section == 1:
                return self.tr("Content")
        return super().headerData(section, orientation, role)

    def flags(self, index) -> Qt.ItemFlags:
        flags = super().flags(index)
        if (
            index.column() == 0
            or index.column() == 1
            and not self.isDir(index)
            and self.filePath(index) not in self.binary_files
        ):
            flags |= Qt.ItemIsUserCheckable
        return flags

    def data(self, index, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.CheckStateRole:
            path = self.filePath(index)
            if index.column() == 0:
                with QMutexLocker(self.mutex):
                    if path in self.check_states:
                        return Qt.CheckState(self.check_states[path])
                    default_state = 0 if _is_sensitive_path(path) else 2
                    self.check_states[path] = default_state
                    return Qt.CheckState(default_state)
            elif index.column() == 1:
                if self.isDir(index) or path in self.binary_files:
                    return None
                with QMutexLocker(self.mutex):
                    return Qt.CheckState(self.content_check_states.get(path, 0))
            return None
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return super().data(index, role)
            if index.column() == 1:
                return ""
        return super().data(index, role)

    def setData(self, index, value: Any, role: int = Qt.CheckStateRole) -> bool:
        if role != Qt.CheckStateRole:
            return super().setData(index, value, role)

        path = self.filePath(index)
        col = index.column()

        if col == 0:
            try:
                new_state = int(value)
            except (ValueError, TypeError):
                return False

            with QMutexLocker(self.mutex):
                old_state = self.check_states.get(path, 0 if _is_sensitive_path(path) else 2)

            if self.isDir(index):
                if old_state == 1 or old_state == 2 and new_state == 0:
                    new_state = 0
                elif old_state == 0 and new_state == 2:
                    new_state = 2

            if old_state != new_state:
                with QMutexLocker(self.mutex):
                    self.check_states[path] = new_state

                self.dataChanged.emit(index, index, [Qt.CheckStateRole])
                self._recalculate_ancestors(path)

                if self.isDir(index) and new_state == 0:
                    self.desc_worker.enqueue(path, 0)

                return True

        elif col == 1 and not self.isDir(index) and path not in self.binary_files:
            try:
                new_state = int(value)
            except (ValueError, TypeError):
                return False

            with QMutexLocker(self.mutex):
                self.content_check_states[path] = new_state
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])

            if new_state == 2:
                vis_index = index.siblingAtColumn(0)
                should_emit_vis = False
                with QMutexLocker(self.mutex):
                    if self.check_states.get(path, 2) == 0:
                        self.check_states[path] = 2
                        should_emit_vis = True

                if should_emit_vis:
                    self.dataChanged.emit(vis_index, vis_index, [Qt.CheckStateRole])
                    self._recalculate_ancestors(path)

            self.content_state_toggled.emit(path, new_state)
            return True

        return super().setData(index, value, role)

    def _recalculate_ancestors(self, start_path: str) -> None:
        current_path = start_path
        while True:
            parent_path = os.path.dirname(current_path)
            if parent_path == current_path or not parent_path:
                break

            try:
                entries = os.listdir(parent_path)
            except (PermissionError, Exception):
                break

            checked_count = 0
            partial_count = 0
            total_valid = 0

            for name in entries:
                child_path = f"{parent_path}/{name}".replace("\\", "/")
                with QMutexLocker(self.mutex):
                    state = self.check_states.get(
                        child_path, 0 if _is_sensitive_path(child_path) else 2
                    )
                if state == 2:
                    checked_count += 1
                elif state == 1:
                    partial_count += 1
                total_valid += 1

            if total_valid > 0 and checked_count == total_valid:
                new_state = 2
            elif checked_count > 0 or partial_count > 0:
                new_state = 1
            else:
                with QMutexLocker(self.mutex):
                    current_parent_state = self.check_states.get(parent_path, 2)
                new_state = 0 if current_parent_state == 0 else 2

            should_emit = False
            with QMutexLocker(self.mutex):
                if self.check_states.get(parent_path, 2) != new_state:
                    self.check_states[parent_path] = new_state
                    should_emit = True

            if should_emit:
                parent_idx = self.index(parent_path)
                if parent_idx.isValid():
                    self.dataChanged.emit(parent_idx, parent_idx, [Qt.CheckStateRole])

            current_path = parent_path

    def _on_descendant_update_finished(self, updated_paths: list[str]) -> None:
        for path in updated_paths:
            idx = self.index(path)
            if idx.isValid():
                self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])

    def _on_content_update_finished(self, updated_paths: list[str]) -> None:
        for path in updated_paths:
            idx = self.index(path)
            if idx.isValid():
                content_idx = idx.siblingAtColumn(1)
                if content_idx.isValid():
                    self.dataChanged.emit(content_idx, content_idx, [Qt.CheckStateRole])
        self.content_state_toggled.emit("BULK_CONTENT_DONE", 0)

    def __del__(self) -> None:
        if getattr(self, "desc_thread", None) and self.desc_thread.isRunning():
            self.desc_thread.quit()
            self.desc_thread.wait()


# ======================================================================
# Sort/Filter Proxy
# ======================================================================
class TreeFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.exclude_dirs: set[str] = set()
        self.allowed_extensions: set[str] | None = None
        self.project_loaded = False

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not self.project_loaded:
            return False
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False
        name = model.fileName(index)

        if model.isDir(index) and name in self.exclude_dirs:
            return False
        if not model.isDir(index) and self.allowed_extensions is not None:
            ext = os.path.splitext(name)[1].lower()
            if ext == "":
                if "<no_ext>" not in self.allowed_extensions:
                    return False
            else:
                if ext not in self.allowed_extensions:
                    return False
        return True


# ======================================================================
# Export Worker
# ======================================================================
class ExportWorker(QObject):
    textReady = Signal(str)
    exportStarted = Signal()
    exportFinished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.queue: deque = deque()
        self.mutex = QMutex()
        self._running = True

    def stop(self) -> None:
        self._running = False

    def enqueue(self, params: tuple) -> None:
        with QMutexLocker(self.mutex):
            self.queue.append(params)
        QTimer.singleShot(0, self.process)

    def process(self) -> None:
        if not self._running:
            return
        params = None
        with QMutexLocker(self.mutex):
            if self.queue:
                params = self.queue.popleft()
        if params:
            self.exportStarted.emit()
            self.do_work(params)
            self.exportFinished.emit()

    def do_work(self, params: tuple) -> None:
        (
            root_path,
            fmt,
            exclude_dirs,
            allowed_extensions,
            check_states,
            content_check_states,
            master_include,
            sort_field,
            sort_descending,
        ) = params
        lines = []
        if fmt == "txt":
            lines.append(QCoreApplication.translate("ExportWorker", "Project Tree Structure"))
            lines.append(QCoreApplication.translate("ExportWorker", "Root: {}").format(root_path))
            lines.append(
                QCoreApplication.translate("ExportWorker", "Date: {}").format(
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            lines.append("=" * 60)
            lines.append("")
        else:
            lines.append(QCoreApplication.translate("ExportWorker", "# Project Tree Structure"))
            lines.append(
                QCoreApplication.translate("ExportWorker", "**Root:** `{}`").format(root_path)
            )
            lines.append(
                QCoreApplication.translate("ExportWorker", "**Date:** {}").format(
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            lines.append("---")
            lines.append("")

        self._walk(
            root_path,
            0,
            lines,
            exclude_dirs,
            allowed_extensions,
            check_states,
            content_check_states,
            master_include,
            fmt,
            sort_field,
            sort_descending,
        )
        self.textReady.emit("\n".join(lines))

    def _walk(
        self,
        current_path: str,
        depth: int,
        lines: list[str],
        exclude_dirs: set[str],
        allowed_extensions: set[str] | None,
        check_states: dict[str, int],
        content_check_states: dict[str, int],
        master_include: bool,
        fmt: str,
        sort_field: str,
        sort_descending: bool,
    ) -> None:
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            logger.warning(f"Permission denied: {current_path}")
            return
        except Exception as e:
            logger.error(f"Error listing {current_path}: {e}")
            return

        entry_objs = []
        for name in entries:
            p = Path(current_path) / name
            full_path = p.as_posix()
            is_dir = p.is_dir()
            if is_dir and name in exclude_dirs:
                continue
            if not is_dir and allowed_extensions is not None:
                ext = os.path.splitext(name)[1].lower()
                if (ext == "" and "<no_ext>" not in allowed_extensions) or (
                    ext != "" and ext not in allowed_extensions
                ):
                    continue

            stat = p.stat() if not is_dir else None
            entry_objs.append(
                {
                    "name": name,
                    "full_path": full_path,
                    "is_dir": is_dir,
                    "ext": os.path.splitext(name)[1].lower(),
                    "mtime": stat.st_mtime if stat else 0,
                    "size": stat.st_size if stat else 0,
                }
            )

        reverse = sort_descending
        if sort_field == "Name":
            entry_objs.sort(key=lambda x: x["name"].lower(), reverse=reverse)
        elif sort_field == "Type":
            entry_objs.sort(key=lambda x: (x["ext"], x["name"].lower()), reverse=reverse)
        elif sort_field == "Date Modified":
            entry_objs.sort(key=lambda x: x["mtime"], reverse=reverse)
        elif sort_field == "Size":
            entry_objs.sort(key=lambda x: x["size"], reverse=reverse)
        else:
            entry_objs.sort(key=lambda x: x["name"].lower())

        indent = "    " * depth
        for entry in entry_objs:
            name, full_path, is_dir = entry["name"], entry["full_path"], entry["is_dir"]
            current_state = check_states.get(full_path, 0 if _is_sensitive_path(full_path) else 2)

            if is_dir:
                if current_state == 0:
                    continue
                lines.append(f"{indent}📂 {name}/" if fmt == "txt" else f"{indent}* **{name}/**")
                self._walk(
                    str(Path(current_path) / name),
                    depth + 1,
                    lines,
                    exclude_dirs,
                    allowed_extensions,
                    check_states,
                    content_check_states,
                    master_include,
                    fmt,
                    sort_field,
                    sort_descending,
                )
            else:
                if current_state != 2:
                    continue
                lines.append(f"{indent}📜 {name}" if fmt == "txt" else f"{indent}* 📄 `{name}`")

                if master_include and content_check_states.get(full_path, 0) == 2:
                    try:
                        with open(full_path, encoding="utf-8", errors="replace") as f:
                            content_indent = indent + "    "
                            if fmt == "md":
                                lines.append(f"{content_indent}```")
                                for line in f:
                                    lines.append(f"{content_indent}{line.rstrip()}")
                                lines.append(f"{content_indent}```")
                            else:
                                lines.append(f"{content_indent}--- BEGIN {name} ---")
                                for line in f:
                                    lines.append(f"{content_indent}{line.rstrip()}")
                                lines.append(f"{content_indent}--- END {name} ---")
                    except Exception as e:
                        logger.error(f"Failed to read file {full_path}: {e}")


# ======================================================================
# Extension Scanner Worker
# ======================================================================
class ExtensionScannerWorker(QObject):
    extensions_ready = Signal(set, bool, set)
    finished = Signal()

    def __init__(self, root_path: str, exclude_dirs: set[str]) -> None:
        super().__init__()
        self.root_path = root_path
        self.exclude_dirs = exclude_dirs

    def run(self) -> None:
        extensions, has_no_ext, binary_files = set(), False, set()
        try:
            for dirpath, dirnames, filenames in os.walk(self.root_path):
                dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]
                for f in filenames:
                    full = os.path.join(dirpath, f)
                    ext = os.path.splitext(f)[1].lower()
                    if is_binary_file(full):
                        binary_files.add(Path(full).as_posix())
                    if ext:
                        extensions.add(ext)
                    else:
                        has_no_ext = True
        except Exception as e:
            logger.error(f"Error during extension scan: {e}")
        self.extensions_ready.emit(extensions, has_no_ext, binary_files)
        self.finished.emit()


# ======================================================================
# Main Application Window
# ======================================================================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(self.tr("Project Tree Generator Pro"))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(1280, 720)
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        self.setMinimumSize(1280, 720)

        self.root_path: str | None = None
        self.current_translator: QTranslator | None = None
        self._latest_version: str | None = None
        self._download_url: str | None = None

        saved_excludes = _app_settings.value("excludedDirs", [])
        if isinstance(saved_excludes, str):
            saved_excludes = [saved_excludes] if saved_excludes else []
        self.exclude_dirs = set(saved_excludes or [])

        self.ext_checkboxes: dict[str, QCheckBox] = {}
        self.allowed_extensions: set[str] | None = None
        self.no_ext_checkbox: QCheckBox | None = None
        self.sort_field, self.sort_descending = "Name", False
        self._scan_in_progress = self._awaiting_export = self._opening_folder = False

        self.fs_model = CheckableFileSystemModel()
        self.fs_model.exclude_dirs = self.exclude_dirs
        self.fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.proxy_model = TreeFilterProxy()
        self.proxy_model.setSourceModel(self.fs_model)

        self.fs_model.content_state_toggled.connect(self._on_content_toggled)

        self.export_thread = QThread()
        self.export_worker = ExportWorker()
        self.export_worker.moveToThread(self.export_thread)
        self.export_worker.textReady.connect(self.export_preview_update)
        self.export_worker.exportStarted.connect(self.on_export_started)
        self.export_worker.exportFinished.connect(self.on_export_finished)
        self.export_thread.start()

        self.export_timer = QTimer()
        self.export_timer.setSingleShot(True)
        self.export_timer.timeout.connect(self.trigger_export_update)

        self.setup_ui()
        self.setup_toolbar()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        self.progress_bar.setMaximumWidth(500)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().setStyleSheet(
            "QStatusBar::item { border: none; }QProgressBar { margin-right: 32px; }"
        )

        if _app_settings.value("language", "en") == "fa":
            QTimer.singleShot(0, self.change_language)

        font_path = os.path.join(_fonts_dir(), "Vazirmatn.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                QApplication.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))

        ico_path = os.path.join(_bundle_path(), "app_icon.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        QTimer.singleShot(2000, self.auto_check_updates)

    def auto_check_updates(self) -> None:
        worker = UpdateWorker("check")
        worker.update_available.connect(self.on_auto_update_available)
        worker.start()
        self._update_worker_ref = worker

    def on_auto_update_available(self, version: str, url: str) -> None:
        self._latest_version = version
        self._download_url = url
        self.about_btn.setText(self.tr("❓ About (Update Available)"))
        self.about_btn.setStyleSheet("color: green; font-weight: bold;")

    def _apply_column_sizing(self) -> None:
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 55)
        QTimer.singleShot(0, lambda: header.setSectionResizeMode(1, QHeaderView.Interactive))
        for col in range(2, self.fs_model.columnCount()):
            self.tree.setColumnHidden(col, True)

    def on_export_started(self) -> None:
        if not self._scan_in_progress:
            self.progress_bar.setValue(0)

    def on_export_finished(self) -> None:
        self.progress_bar.setValue(100)
        QTimer.singleShot(200, self._reset_progress_bar)

    def _reset_progress_bar(self) -> None:
        self.progress_bar.setValue(0)
        self._scan_in_progress = self._awaiting_export = False

    def _on_content_toggled(self, path: str, new_state: int) -> None:
        if path == "BULK_CONTENT_DONE":
            self.progress_bar.setValue(100)
            QTimer.singleShot(200, self._reset_progress_bar)
            self.schedule_export_update()
            return

        if new_state == 2 and not self.master_include_cb.isChecked():
            self.master_include_cb.setChecked(True)
        elif (
            not any(s == 2 for s in self.fs_model.content_check_states.values())
            and self.master_include_cb.isChecked()
        ):
            self.master_include_cb.setChecked(False)
        self.schedule_export_update()

    def setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        self.filter_group = QGroupBox(self.tr("File Type Filters"))
        filter_layout = QVBoxLayout()
        self.ext_checkboxes_widget = QWidget()
        self.ext_checkboxes_layout = QGridLayout(self.ext_checkboxes_widget)
        filter_layout.addWidget(self.ext_checkboxes_widget)

        btn_layout = QHBoxLayout()
        self.all_ext_btn = QPushButton(self.tr("All"))
        self.none_ext_btn = QPushButton(self.tr("None"))
        btn_layout.addWidget(self.all_ext_btn)
        btn_layout.addWidget(self.none_ext_btn)
        filter_layout.addLayout(btn_layout)
        self.filter_group.setLayout(filter_layout)
        left_layout.addWidget(self.filter_group)

        self.tree = QTreeView()
        self.tree.setAnimated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(False)
        self.tree.clicked.connect(self.on_tree_clicked)
        left_layout.addWidget(self.tree)

        self.export_preview = QTextEdit()
        self.export_preview.setReadOnly(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.export_preview)
        splitter.setSizes([500, 725])
        main_layout.addWidget(splitter)

        self.all_ext_btn.clicked.connect(lambda: self.set_all_extensions(True))
        self.none_ext_btn.clicked.connect(lambda: self.set_all_extensions(False))

    def setup_toolbar(self) -> None:
        toolbar = QToolBar(self.tr("Main"))
        self.addToolBar(toolbar)

        self.open_btn = QPushButton(self.tr("📂 Open Folder"))
        self.open_btn.clicked.connect(self.open_folder)
        toolbar.addWidget(self.open_btn)
        toolbar.addSeparator()

        self.format_group = QButtonGroup()
        self.txt_radio = QRadioButton("TXT")
        self.md_radio = QRadioButton("Markdown")
        self.txt_radio.setChecked(True)
        self.format_group.addButton(self.txt_radio)
        self.format_group.addButton(self.md_radio)
        toolbar.addWidget(self.txt_radio)
        toolbar.addWidget(self.md_radio)

        self.save_btn = QPushButton(self.tr("💾 Save Export"))
        self.save_btn.clicked.connect(self.save_export)
        toolbar.addWidget(self.save_btn)
        toolbar.addSeparator()

        self.master_include_cb = QCheckBox(self.tr("Include file contents"))
        self.master_include_cb.setChecked(False)
        self.master_include_cb.setEnabled(False)
        toolbar.addWidget(self.master_include_cb)

        self.all_content_btn = QPushButton(self.tr("All Content"))
        self.none_content_btn = QPushButton(self.tr("None Content"))
        self.all_content_btn.clicked.connect(lambda: self.set_all_content(True))
        self.none_content_btn.clicked.connect(lambda: self.set_all_content(False))
        toolbar.addWidget(self.all_content_btn)
        toolbar.addWidget(self.none_content_btn)
        toolbar.addSeparator()

        self.sort_btn = QPushButton(self.tr("Sort Options"))
        sort_menu = QMenu(self)
        self.sort_action_group = QActionGroup(sort_menu)
        self.sort_action_group.setExclusive(True)
        self.sort_actions: dict[str, Any] = {}
        for field in ["Name", "Type", "Date Modified", "Size"]:
            action = sort_menu.addAction(self.tr(field))
            action.setCheckable(True)
            self.sort_action_group.addAction(action)
            self.sort_actions[field] = action
            action.triggered.connect(lambda _, f=field: self.on_sort_field_changed(f))

        sort_menu.addSeparator()
        self.order_action_group = QActionGroup(sort_menu)
        self.order_action_group.setExclusive(True)
        self.asc_action = sort_menu.addAction(self.tr("Ascending"))
        self.asc_action.setCheckable(True)
        self.desc_action = sort_menu.addAction(self.tr("Descending"))
        self.desc_action.setCheckable(True)
        self.order_action_group.addAction(self.asc_action)
        self.order_action_group.addAction(self.desc_action)
        self.asc_action.triggered.connect(lambda: self.on_order_changed(False))
        self.desc_action.triggered.connect(lambda: self.on_order_changed(True))

        self.sort_actions["Name"].setChecked(True)
        self.asc_action.setChecked(True)
        self.sort_btn.setMenu(sort_menu)
        toolbar.addWidget(self.sort_btn)
        toolbar.addSeparator()

        self.exclude_btn = QPushButton(self.tr("⚙️ Exclude Dirs"))
        self.exclude_btn.clicked.connect(self.edit_excludes)
        toolbar.addWidget(self.exclude_btn)
        toolbar.addSeparator()

        self.lang_label = QLabel(self.tr("Language: "))
        toolbar.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "فارسی"])
        self.lang_combo.setCurrentText(
            "فارسی" if _app_settings.value("language", "en") == "fa" else "English"
        )
        self.lang_combo.currentIndexChanged.connect(self.change_language)
        toolbar.addWidget(self.lang_combo)

        toolbar.addSeparator()
        self.about_btn = QPushButton(self.tr("❓ About"))
        self.about_btn.clicked.connect(self.show_about)
        toolbar.addWidget(self.about_btn)

        self.txt_radio.toggled.connect(lambda: self.schedule_export_update())
        self.md_radio.toggled.connect(lambda: self.schedule_export_update())
        self.fs_model.dataChanged.connect(lambda: self.schedule_export_update())

    def show_about(self) -> None:
        dialog = AboutDialog(self)
        if self._latest_version and self._download_url:
            dialog._download_url = self._download_url
            dialog.update_btn.setText(self.tr("Download Update"))
            dialog.status_label.setText(
                self.tr("Update available: Version {}").format(self._latest_version)
            )
            dialog.status_label.setStyleSheet("color: green; font-weight: bold;")
        dialog.exec()

    def on_sort_field_changed(self, field: str) -> None:
        self.sort_field = field
        self.schedule_export_update()

    def on_order_changed(self, descending: bool) -> None:
        self.sort_descending = descending
        self.schedule_export_update()

    def change_language(self) -> None:
        lang = "fa" if self.lang_combo.currentText() == "فارسی" else "en"
        app = QApplication.instance()
        for translator in app.findChildren(QTranslator):
            app.removeTranslator(translator)
        self.current_translator = None

        if lang == "fa":
            translator = QTranslator()
            if translator.load(os.path.join(_translations_dir(), "fa.qm")):
                app.installTranslator(translator)
                self.current_translator = translator
            else:
                logger.error("Could not load Persian translation.")
                QMessageBox.warning(
                    self, self.tr("Error"), self.tr("Could not load Persian translation.")
                )
                return

        _app_settings.setValue("language", lang)
        QCoreApplication.sendEvent(app, QEvent(QEvent.LanguageChange))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.tr("Project Tree Generator Pro"))
        self.filter_group.setTitle(self.tr("File Type Filters"))
        self.all_ext_btn.setText(self.tr("All"))
        self.none_ext_btn.setText(self.tr("None"))
        self.open_btn.setText(self.tr("📂 Open Folder"))
        self.save_btn.setText(self.tr("💾 Save Export"))
        self.master_include_cb.setText(self.tr("Include file contents"))
        self.all_content_btn.setText(self.tr("All Content"))
        self.none_content_btn.setText(self.tr("None Content"))
        self.exclude_btn.setText(self.tr("⚙️ Exclude Dirs"))
        self.sort_btn.setText(self.tr("Sort Options"))
        self.lang_label.setText(self.tr("Language: "))
        self.about_btn.setText(self.tr("❓ About"))
        for eng, fa in [
            ("Name", self.tr("Name")),
            ("Type", self.tr("Type")),
            ("Date Modified", self.tr("Date Modified")),
            ("Size", self.tr("Size")),
        ]:
            self.sort_actions[eng].setText(fa)
        self.asc_action.setText(self.tr("Ascending"))
        self.desc_action.setText(self.tr("Descending"))
        if self.no_ext_checkbox:
            self.no_ext_checkbox.setText(self.tr("No extension"))
        self.fs_model.headerDataChanged.emit(Qt.Horizontal, 0, 1)

    def schedule_export_update(self) -> None:
        self.export_timer.start(300)

    def trigger_export_update(self) -> None:
        if not self.root_path:
            return
        fmt = "md" if self.md_radio.isChecked() else "txt"
        params = (
            self.root_path,
            fmt,
            self.exclude_dirs,
            self.allowed_extensions,
            self.fs_model.check_states.copy(),
            self.fs_model.content_check_states.copy(),
            self.master_include_cb.isChecked(),
            self.sort_field,
            self.sort_descending,
        )
        self.export_worker.enqueue(params)

    def export_preview_update(self, text: str) -> None:
        self.export_preview.setPlainText(text)

    def open_folder(self) -> None:
        last_dir = _app_settings.value("last_open_dir", "")
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select Project Folder"), last_dir)
        if not folder:
            return

        _app_settings.setValue("last_open_dir", folder)
        self.root_path = folder

        with QMutexLocker(self.fs_model.mutex):
            self.fs_model.check_states.clear()
            self.fs_model.content_check_states.clear()
            self.fs_model.binary_files.clear()

        self.tree.setModel(None)
        self.tree.setUpdatesEnabled(False)
        self.statusBar().showMessage(self.tr("Scanning file types..."))
        self._opening_folder = True
        self.fs_model.setRootPath(folder)
        self.collect_extensions()

    def collect_extensions(self) -> None:
        self.ext_scan_thread = QThread()
        self.ext_scan_worker = ExtensionScannerWorker(self.root_path, self.exclude_dirs)
        self.ext_scan_worker.moveToThread(self.ext_scan_thread)
        self.ext_scan_worker.extensions_ready.connect(self.setup_extension_filters)
        self.ext_scan_worker.finished.connect(self.ext_scan_thread.quit)
        self.ext_scan_worker.finished.connect(self.ext_scan_worker.deleteLater)
        self.ext_scan_thread.started.connect(self.ext_scan_worker.run)
        self.ext_scan_thread.start()

    def setup_extension_filters(
        self, extensions: set[str], has_no_ext: bool, binary_files: set[str]
    ) -> None:
        while self.ext_checkboxes_layout.count():
            item = self.ext_checkboxes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.ext_checkboxes.clear()
        self.no_ext_checkbox = None

        with QMutexLocker(self.fs_model.mutex):
            self.fs_model.binary_files = binary_files

        row, col = 0, 0
        for ext in sorted(list(extensions)):
            cb = QCheckBox(ext)
            cb.setChecked(True)
            cb.toggled.connect(self.on_extension_filter_changed)
            self.ext_checkboxes_layout.addWidget(cb, row, col)
            self.ext_checkboxes[ext] = cb
            col += 1
            if col >= 4:
                col = 0
                row += 1

        if has_no_ext:
            self.no_ext_checkbox = QCheckBox(self.tr("No extension"))
            self.no_ext_checkbox.setChecked(True)
            self.no_ext_checkbox.toggled.connect(self.on_extension_filter_changed)
            self.ext_checkboxes_layout.addWidget(self.no_ext_checkbox, row, col)
            self.ext_checkboxes["<no_ext>"] = self.no_ext_checkbox

        self.allowed_extensions = set(extensions)
        if has_no_ext:
            self.allowed_extensions.add("<no_ext>")

        self.proxy_model.allowed_extensions = self.allowed_extensions
        self.proxy_model.exclude_dirs = self.exclude_dirs
        self.proxy_model.project_loaded = True
        self.proxy_model.invalidate()

        if self.root_path:
            proxy_root = self.proxy_model.mapFromSource(self.fs_model.index(self.root_path))
            self.tree.setModel(self.proxy_model)
            self.tree.setRootIndex(proxy_root)
            self._apply_column_sizing()
            self.tree.setUpdatesEnabled(True)

        self.statusBar().clearMessage()
        self.schedule_export_update()

    def on_extension_filter_changed(self) -> None:
        self.allowed_extensions = {key for key, cb in self.ext_checkboxes.items() if cb.isChecked()}
        self.proxy_model.allowed_extensions = self.allowed_extensions
        self.proxy_model.invalidate()
        self.schedule_export_update()

    def set_all_extensions(self, state: bool) -> None:
        for cb in self.ext_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(state)
            cb.blockSignals(False)
        self.allowed_extensions = set(self.ext_checkboxes.keys()) if state else set()
        self.proxy_model.allowed_extensions = self.allowed_extensions
        self.proxy_model.invalidate()
        self.schedule_export_update()

    def set_all_content(self, state: bool) -> None:
        if not self.root_path:
            return
        if state and not self.master_include_cb.isChecked():
            self.master_include_cb.setChecked(True)
        elif not state and self.master_include_cb.isChecked():
            self.master_include_cb.setChecked(False)

        if state:
            self._scan_in_progress = True
            self.progress_bar.setValue(0)
            QMetaObject.invokeMethod(
                self.fs_model.desc_worker,
                "set_all_content_states",
                Qt.QueuedConnection,
                Q_ARG(str, self.root_path),
                Q_ARG(int, 2),
            )
        else:
            self.fs_model.desc_worker.content_canceled = True

            with QMutexLocker(self.fs_model.mutex):
                self.fs_model.content_check_states.clear()
            root_idx = self.fs_model.index(self.root_path)
            if root_idx.isValid():
                self.fs_model.dataChanged.emit(root_idx, root_idx, [Qt.CheckStateRole])
            self.schedule_export_update()

    def on_tree_clicked(self, index) -> None:
        pass

    def save_export(self) -> None:
        if not self.root_path:
            QMessageBox.warning(self, self.tr("Error"), self.tr("No project loaded."))
            return
        fmt = "md" if self.md_radio.isChecked() else "txt"
        last_save_dir = _app_settings.value("last_save_dir", "")
        if not last_save_dir or not os.path.isdir(last_save_dir):
            last_save_dir = os.path.expanduser("~")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Export"),
            os.path.join(last_save_dir, f"project_structure.{fmt}"),
            self.tr("Text Files (*.txt);;Markdown Files (*.md)"),
        )
        if not file_path:
            return

        _app_settings.setValue("last_save_dir", os.path.dirname(file_path))
        text = self.export_preview.toPlainText()
        if not text.strip():
            QMessageBox.warning(
                self, self.tr("Warning"), self.tr("Export preview is empty. Nothing to save.")
            )
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(
                self, self.tr("Success"), self.tr("Saved to {}").format(file_path)
            )
        except Exception as e:
            logger.error(f"Failed to save export: {e}")
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to save: {}").format(e))

    def edit_excludes(self) -> None:
        dialog = ExcludeDirsDialog(self.exclude_dirs, self)
        if dialog.exec():
            self.exclude_dirs = dialog.get_excludes()
            _app_settings.setValue("excludedDirs", list(self.exclude_dirs))
            _app_settings.sync()

            self.fs_model.exclude_dirs = self.exclude_dirs

            self.proxy_model.exclude_dirs = self.exclude_dirs
            self.proxy_model.invalidate()
            self.schedule_export_update()

    def closeEvent(self, event) -> None:
        logger.info("Application shutting down.")
        self.export_worker.stop()
        self.export_thread.quit()
        self.export_thread.wait()
        self.fs_model.desc_thread.quit()
        self.fs_model.desc_thread.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Project Tree Generator Pro")

    ico_path = os.path.join(_bundle_path(), "app_icon.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    logger.info("Application started.")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
