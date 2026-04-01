"""
Total Commander Clone - File Operations
Provides threaded copy, move, and delete operations with
progress dialogs, conflict resolution (overwrite/cancel/keep both),
and proper error handling.
"""

import os
import shutil

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QMessageBox, QApplication, QCheckBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMutex, QWaitCondition


# Conflict resolution choices (used between worker and main thread)
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_CANCEL = "cancel"
CONFLICT_KEEP_BOTH = "keep_both"


class UserAbortError(Exception):
    """Raised when the user cancels the file operation from a conflict dialog."""


def _resolveConflictPath(dest_path):
    """Return a conflict-free path by appending (1), (2), etc."""
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(dest_path)
    counter = 1
    while os.path.exists(dest_path):
        dest_path = f"{base} ({counter}){ext}"
        counter += 1
    return dest_path


# ============================================================
# Class: ConflictDialog
# Purpose: Modal dialog when a file already exists at destination.
#          Options: Overwrite, Cancel operation, Keep both (rename).
#          Checkbox: "Do this for all files".
# ============================================================
class ConflictDialog(QDialog):

    def __init__(self, file_name, dest_dir, operation_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Already Exists")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._choice = None
        self._new_dest_path = None
        self._apply_to_all = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        msg = QLabel(
            f"A file named \"{file_name}\" already exists in the destination.\n"
            f"What do you want to do?"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self._chk_apply_all = QCheckBox("Do this for all files")
        layout.addWidget(self._chk_apply_all)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_overwrite = QPushButton("Overwrite")
        self._btn_overwrite.clicked.connect(self._onOverwrite)
        btn_layout.addWidget(self._btn_overwrite)

        self._btn_keep_both = QPushButton("Keep both")
        self._btn_keep_both.setToolTip("Keep the existing file and copy with a new name")
        self._btn_keep_both.clicked.connect(self._onKeepBoth)
        btn_layout.addWidget(self._btn_keep_both)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self._onCancel)
        btn_layout.addWidget(self._btn_cancel)

        layout.addLayout(btn_layout)

    def _onOverwrite(self):
        self._choice = CONFLICT_OVERWRITE
        self._apply_to_all = self._chk_apply_all.isChecked()
        self.accept()

    def _onKeepBoth(self):
        self._choice = CONFLICT_KEEP_BOTH
        self._apply_to_all = self._chk_apply_all.isChecked()
        self.accept()

    def _onCancel(self):
        self._choice = CONFLICT_CANCEL
        self._apply_to_all = self._chk_apply_all.isChecked()
        self.accept()

    def getChoice(self):
        """Returns (choice, apply_to_all). choice is CONFLICT_OVERWRITE, CONFLICT_CANCEL, or CONFLICT_KEEP_BOTH."""
        return self._choice, self._apply_to_all


# ============================================================
# Class: FileOperationWorker
# Purpose: QThread worker that performs copy/move/delete
#          operations in the background. For copy/move, when a
#          file already exists it signals the main thread to show
#          a conflict dialog and waits for the user's choice.
# ============================================================
class FileOperationWorker(QThread):

    progressChanged = pyqtSignal(int, str)
    operationFinished = pyqtSignal(bool, str)
    errorOccurred = pyqtSignal(str, str)
    conflictDetected = pyqtSignal(str, str, str)

    OPERATION_COPY = "copy"
    OPERATION_MOVE = "move"
    OPERATION_DELETE = "delete"

    # --------------------------------------------------------
    # Method: __init__
    # --------------------------------------------------------
    def __init__(self, operation, file_paths, destination="", parent=None):
        super().__init__(parent)
        self._operation = operation
        self._file_paths = file_paths
        self._destination = destination
        self._cancelled = False
        self._errors = []
        self._conflict_mutex = QMutex()
        self._conflict_condition = QWaitCondition()
        self._conflict_choice = None
        self._conflict_new_dest = None
        self._apply_to_all_choice = None

    # --------------------------------------------------------
    # Method: cancel
    # --------------------------------------------------------
    def cancel(self):
        self._cancelled = True

    # --------------------------------------------------------
    # Method: setConflictResponse
    # Purpose: Called from the main thread after user chooses.
    #          choice: CONFLICT_OVERWRITE | CONFLICT_CANCEL | CONFLICT_KEEP_BOTH
    #          new_dest: used when choice is KEEP_BOTH (can be None to auto-rename).
    # --------------------------------------------------------
    def setConflictResponse(self, choice, new_dest=None, apply_to_all=False):
        self._conflict_mutex.lock()
        self._conflict_choice = choice
        self._conflict_new_dest = new_dest
        if apply_to_all:
            self._apply_to_all_choice = choice
        self._conflict_condition.wakeOne()
        self._conflict_mutex.unlock()

    # --------------------------------------------------------
    # Method: run
    # --------------------------------------------------------
    def run(self):
        total = len(self._file_paths)
        if total == 0:
            self.operationFinished.emit(True, "No files to process.")
            return

        for i, source_path in enumerate(self._file_paths):
            if self._cancelled:
                self.operationFinished.emit(False, "Operation cancelled.")
                return

            file_name = os.path.basename(source_path)
            progress_pct = int((i / total) * 100)
            self.progressChanged.emit(progress_pct, file_name)

            try:
                if self._operation == self.OPERATION_COPY:
                    self._copyItem(source_path, self._destination)
                elif self._operation == self.OPERATION_MOVE:
                    self._moveItem(source_path, self._destination)
                elif self._operation == self.OPERATION_DELETE:
                    self._deleteItem(source_path)
            except UserAbortError:
                self.operationFinished.emit(False, "Operation cancelled.")
                return
            except Exception as e:
                error_msg = f"{file_name}: {str(e)}"
                self._errors.append(error_msg)
                self.errorOccurred.emit(file_name, str(e))

        if self._errors:
            error_summary = "\n".join(self._errors)
            self.operationFinished.emit(False, f"Completed with errors:\n{error_summary}")
        else:
            self.progressChanged.emit(100, "Done")
            self.operationFinished.emit(True, f"Successfully processed {total} item(s).")

    # --------------------------------------------------------
    # Method: _askConflict
    # Purpose: Emit signal and block until main thread sets response.
    # Returns: (dest_path to use, or None if operation should be cancelled)
    # --------------------------------------------------------
    def _askConflict(self, source_path, dest_path, file_name):
        if self._apply_to_all_choice is not None:
            choice = self._apply_to_all_choice
            if choice == CONFLICT_CANCEL:
                raise UserAbortError()
            if choice == CONFLICT_OVERWRITE:
                return dest_path
            if choice == CONFLICT_KEEP_BOTH:
                return _resolveConflictPath(dest_path)
            return dest_path

        self.conflictDetected.emit(source_path, dest_path, file_name)
        self._conflict_mutex.lock()
        self._conflict_condition.wait(self._conflict_mutex)
        choice = self._conflict_choice
        new_dest = self._conflict_new_dest
        self._conflict_choice = None
        self._conflict_new_dest = None
        self._conflict_mutex.unlock()

        if choice == CONFLICT_CANCEL:
            raise UserAbortError()
        if choice == CONFLICT_OVERWRITE:
            return dest_path
        if choice == CONFLICT_KEEP_BOTH:
            return new_dest if new_dest else _resolveConflictPath(dest_path)
        return dest_path

    # --------------------------------------------------------
    # Method: _copyItem
    # --------------------------------------------------------
    def _copyItem(self, source, dest_dir):
        name = os.path.basename(source)
        dest_path = os.path.join(dest_dir, name)

        if os.path.exists(dest_path):
            dest_path = self._askConflict(source, dest_path, name)
            if dest_path is None:
                raise UserAbortError()

        if os.path.isdir(source):
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(source, dest_path)
        else:
            shutil.copy2(source, dest_path)

    # --------------------------------------------------------
    # Method: _moveItem
    # --------------------------------------------------------
    def _moveItem(self, source, dest_dir):
        name = os.path.basename(source)
        dest_path = os.path.join(dest_dir, name)

        if os.path.exists(dest_path):
            dest_path = self._askConflict(source, dest_path, name)
            if dest_path is None:
                raise UserAbortError()

        if os.path.exists(dest_path):
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            else:
                os.remove(dest_path)
        shutil.move(source, dest_path)

    # --------------------------------------------------------
    # Method: _deleteItem
    # Purpose: Deletes a file or directory. Uses send2trash
    #          to move to the Recycle Bin when available.
    # --------------------------------------------------------
    def _deleteItem(self, path):
        try:
            from send2trash import send2trash
            send2trash(path)
        except ImportError:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

# ============================================================
# Class: FileOperationDialog
# Purpose: Modal progress dialog shown during long file
#          operations (copy, move, delete). Runs the worker
#          thread and reports progress.
# ============================================================
class FileOperationDialog(QDialog):

    # --------------------------------------------------------
    # Method: __init__
    # Input:  operation (str) - "copy", "move", or "delete"
    #         file_paths (list) - Source paths.
    #         destination (str) - Target directory (ignored for delete).
    #         parent - Parent widget.
    # --------------------------------------------------------
    def __init__(self, operation, file_paths, destination="", parent=None):
        super().__init__(parent)
        self._operation = operation
        self._file_paths = file_paths
        self._destination = destination
        self._result_success = False
        self._result_message = ""

        self._initUI()
        self._startOperation()

    # --------------------------------------------------------
    # Method: _initUI
    # --------------------------------------------------------
    def _initUI(self):
        op_titles = {
            "copy": "Copying Files",
            "move": "Moving Files",
            "delete": "Deleting Files",
        }
        self.setWindowTitle(op_titles.get(self._operation, "File Operation"))
        self.setMinimumWidth(450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._title_label = QLabel(f"{op_titles.get(self._operation, 'Processing')}...")
        self._title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._title_label)

        self._file_label = QLabel("Preparing...")
        layout.addWidget(self._file_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._count_label = QLabel(f"0 / {len(self._file_paths)} items")
        layout.addWidget(self._count_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._onCancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    # --------------------------------------------------------
    # Method: _startOperation
    # --------------------------------------------------------
    def _startOperation(self):
        self._worker = FileOperationWorker(
            self._operation, self._file_paths, self._destination, self
        )
        self._worker.progressChanged.connect(self._onProgress)
        self._worker.operationFinished.connect(self._onFinished)
        self._worker.errorOccurred.connect(self._onError)
        if self._operation in (FileOperationWorker.OPERATION_COPY, FileOperationWorker.OPERATION_MOVE):
            self._worker.conflictDetected.connect(self._onConflictDetected)
        self._worker.start()

    # --------------------------------------------------------
    # Method: _onConflictDetected
    # Purpose: Show conflict dialog and send user's choice to worker.
    # --------------------------------------------------------
    def _onConflictDetected(self, source_path, dest_path, file_name):
        dest_dir = os.path.dirname(dest_path)
        op_name = "Copy" if self._operation == FileOperationWorker.OPERATION_COPY else "Move"
        dialog = ConflictDialog(file_name, dest_dir, op_name, self)
        if dialog.exec_() != QDialog.Accepted:
            self._worker.setConflictResponse(CONFLICT_CANCEL, apply_to_all=False)
            return
        choice, apply_to_all = dialog.getChoice()
        if not choice:
            self._worker.setConflictResponse(CONFLICT_CANCEL, apply_to_all=False)
            return
        new_dest = None
        if choice == CONFLICT_KEEP_BOTH:
            new_dest = _resolveConflictPath(dest_path)
        self._worker.setConflictResponse(choice, new_dest, apply_to_all)

    # --------------------------------------------------------
    # Slots
    # --------------------------------------------------------
    def _onProgress(self, percent, file_name):
        self._progress_bar.setValue(percent)
        self._file_label.setText(f"Processing: {file_name}")
        total = len(self._file_paths)
        done = int(percent * total / 100) if total else 0
        self._count_label.setText(f"{done} / {total} items")

    def _onFinished(self, success, message):
        self._result_success = success
        self._result_message = message
        self.accept()

    def _onError(self, file_name, error_msg):
        self._file_label.setText(f"Error: {file_name} - {error_msg}")

    def _onCancel(self):
        self._worker.cancel()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling...")

    # --------------------------------------------------------
    # Public: result accessors
    # --------------------------------------------------------
    def wasSuccessful(self):
        return self._result_success

    def resultMessage(self):
        return self._result_message


# ============================================================
# Module-Level Convenience Functions
# Purpose: Simple wrappers that show a confirmation dialog,
#          run the operation, and return the result.
# ============================================================

def copyFiles(file_paths, destination, parent=None):
    """
    Shows a progress dialog and copies files to destination.
    Returns (success: bool, message: str).
    """
    if not file_paths:
        return True, "No files selected."

    dialog = FileOperationDialog("copy", file_paths, destination, parent)
    dialog.exec_()
    return dialog.wasSuccessful(), dialog.resultMessage()


# ------------------------------------------------------------
def moveFiles(file_paths, destination, parent=None):
    """
    Shows a progress dialog and moves files to destination.
    Returns (success: bool, message: str).
    """
    if not file_paths:
        return True, "No files selected."

    dialog = FileOperationDialog("move", file_paths, destination, parent)
    dialog.exec_()
    return dialog.wasSuccessful(), dialog.resultMessage()


# ------------------------------------------------------------
def deleteFiles(file_paths, parent=None, confirm=True):
    """
    Optionally confirms, then deletes files (to Recycle Bin).
    Returns (success: bool, message: str).
    """
    if not file_paths:
        return True, "No files selected."

    if confirm:
        names = "\n".join(os.path.basename(p) for p in file_paths[:10])
        if len(file_paths) > 10:
            names += f"\n... and {len(file_paths) - 10} more"

        reply = QMessageBox.question(
            parent,
            "Confirm Delete",
            f"Are you sure you want to delete {len(file_paths)} item(s)?\n\n{names}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False, "Delete cancelled."

    dialog = FileOperationDialog("delete", file_paths, "", parent)
    dialog.exec_()
    return dialog.wasSuccessful(), dialog.resultMessage()


# ------------------------------------------------------------
def renameFile(old_path, new_name, parent=None):
    """
    Renames a single file or directory.
    Returns (success: bool, new_path: str, message: str).
    """
    directory = os.path.dirname(old_path)
    new_path = os.path.join(directory, new_name)

    if os.path.exists(new_path):
        return False, old_path, f"'{new_name}' already exists."

    try:
        os.rename(old_path, new_path)
        return True, new_path, "Renamed successfully."
    except OSError as e:
        return False, old_path, str(e)
