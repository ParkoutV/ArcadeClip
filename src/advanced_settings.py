"""Settings view; values are applied only through its owning window."""
from i18n import tr
import os
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit,
                               QHBoxLayout, QLabel, QDialogButtonBox, QFileDialog, QMessageBox, QPushButton, QTabWidget, QWidget)


def show_advanced(window):
    if window.advanced:
        window.advanced.show()
        window.advanced.raise_()
        return
    window.advanced = QDialog(window)
    window.advanced.setWindowTitle(tr('Settings'))
    window.advanced.resize(700, 560)
    layout = QVBoxLayout(window.advanced)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    settings = QSettings("ArcadeClip", "ArcadeClip")

    def page(title):
        """A tab whose groups sit at the top instead of spreading down the dialog."""
        holder = QWidget()
        inner = QVBoxLayout(holder)
        tabs.addTab(holder, title)
        return inner

    general = page(tr('일반'))
    language = QComboBox()
    language.setObjectName("ui_language")
    language.setAccessibleName(tr('Language'))
    language.addItem("한국어", "ko")
    language.addItem("English", "en")
    selected = settings.value("language", os.environ.get("ARCADECLIP_LANGUAGE", "ko"))
    language.setCurrentIndex(1 if str(selected).startswith("en") else 0)

    def change_language():
        settings.setValue("language", language.currentData())
        QMessageBox.information(window.advanced, tr('Language'),
                                tr('언어 변경은 앱을 다시 실행하면 적용됩니다.'))

    language.currentIndexChanged.connect(change_language)
    language_form = QFormLayout()
    language_form.addRow(tr('Language'), language)
    language_hint = QLabel(tr('언어 변경은 앱을 다시 실행하면 적용됩니다.'))
    language_hint.setWordWrap(True)
    language_form.addRow(language_hint)
    general.addLayout(language_form)
    navigation = QGroupBox(tr('화면 탐색'))
    navigation_layout = QVBoxLayout(navigation)
    navigation_layout.addWidget(window.follow_clip)
    window.follow_clip.show()
    general.addWidget(navigation)
    storage = QGroupBox(tr('데이터 저장 위치'))
    storage_layout = QVBoxLayout(storage)
    path = QLineEdit(str(window.directory))
    path.setReadOnly(True)
    path.setAccessibleName(tr('현재 데이터 폴더'))
    storage_layout.addWidget(path)
    window.button(tr('데이터 폴더 변경…'), window.configure, storage_layout)
    general.addWidget(storage)
    general.addStretch()

    catalog = page(tr('자켓 데이터'))
    from jacket_source_ui import fill_catalog_group
    if not getattr(window, "catalog_ready", False):
        fill_catalog_group(window, settings)
        window.catalog_ready = True
    else:
        window.catalog_sources()
    catalog.addWidget(window.catalog)
    window.catalog.show()
    catalog.addStretch()

    reading = page(tr('인식'))
    for group in window.profile.recognition_groups(window.advanced):
        reading.addWidget(group)
    performance = QGroupBox(tr('분석 성능'))
    form = QFormLayout(performance)
    form.addRow(tr('영상 디코더 스레드'), window.decoder_threads)
    window.decoder_threads.show()
    form.addRow(tr('자켓 판독 프로세스'), window.analysis_workers)
    window.analysis_workers.show()
    form.addRow(tr('글자 인식 작업자 (각 2 CPU 스레드)'), window.ocr_workers)
    window.ocr_workers.show()
    form.addRow(QLabel(tr('GPU·겹쳐 처리 옵션은 3번 인식 영역 화면에서 변경합니다.')))
    reading.addWidget(performance)
    performance_hint = QLabel(tr('분석 성능 설정은 다음 분석부터 적용됩니다.'))
    performance_hint.setWordWrap(True)
    reading.addWidget(performance_hint)
    reading.addStretch()

    checks = page(tr('진단'))
    diagnostics = QGroupBox(tr('진단 로그'))
    diagnostic_layout = QVBoxLayout(diagnostics)
    diagnostic_layout.addWidget(window.log)
    row = QHBoxLayout()
    window.button(tr('FFmpeg·다운로드 도구 확인'), window.check_tools, row, busy=False)
    window.button(tr('문제 신고'), lambda: _report_problem(window), row, busy=False)
    diagnostic_layout.addLayout(row)
    report_hint = QLabel(tr('문제 신고는 브라우저에서 열립니다. 위 진단 로그의 내용을 함께 붙여 주세요.'))
    report_hint.setWordWrap(True)
    diagnostic_layout.addWidget(report_hint)
    checks.addWidget(diagnostics, 1)

    about = page(tr('정보'))
    about.addWidget(_version_group(window))
    notices = QGroupBox(tr('오픈소스 라이선스'))
    notices_layout = QVBoxLayout(notices)
    from license_dialog import show_licenses
    window.button(tr('오픈소스 라이선스 보기'), lambda: show_licenses(window.advanced),
                  notices_layout, busy=False)
    about.addWidget(notices)
    about.addStretch()

    buttons = QDialogButtonBox()
    buttons.addButton(tr('닫기'), QDialogButtonBox.ButtonRole.RejectRole)
    buttons.rejected.connect(window.advanced.close)
    layout.addWidget(buttons)
    window.advanced.show()


def _version_group(window):
    from updates import VERSION
    group = QGroupBox(tr('앱 버전'))
    group_layout = QVBoxLayout(group)
    status = QLabel(tr('현재 버전 {name}', name=VERSION))
    status.setWordWrap(True)
    row = QHBoxLayout()
    check = window.button(tr('새 버전 확인'), lambda: _check_updates(window, status, check), row, busy=False)
    window.button(tr('설치 파일(.exe/.zip)로 업데이트…'), lambda: _install_local_update(window, status), row, busy=False)
    group_layout.addLayout(row)
    group_layout.addWidget(status)
    return group


def _launch_installer_and_close(window, installer_path: Path, args: list[str], status: QLabel):
    try:
        window.save_recovery()
    except Exception:
        pass
    started, _ = QProcess.startDetached(str(installer_path), args, str(installer_path.parent))
    if started:
        status.setText(tr('업데이트 설치 프로그램을 실행했습니다. 잠시 후 앱이 자동으로 종료됩니다.'))
        if window.advanced:
            window.advanced.close()
        window.close()
    else:
        QMessageBox.warning(window.advanced or window, tr('업데이트 실행 실패'),
                            tr('설치 파일을 실행하지 못했습니다. 파일을 직접 실행해 주세요: {path}', path=installer_path))


def _download_and_apply_release(window, info: dict, status: QLabel, check: QPushButton):
    from tasks import Task
    from updates import download_installer, installer_upgrade_args
    installer_url = info.get("installer_url")
    if not installer_url:
        QDesktopServices.openUrl(QUrl(info.get("url") or ""))
        return
    check.setEnabled(False)
    updates_dir = window.directory / "updates"
    app_root = Path(__file__).resolve().parents[1]
    task = Task(lambda cancel, report: download_installer(installer_url, updates_dir, cancel, report), window.advanced)
    task.progress.connect(status.setText)

    def finished():
        check.setEnabled(True)
        if task.error:
            status.setText(tr('업데이트 다운로드 실패: {error}', error=task.error))
        elif task.result:
            _launch_installer_and_close(window, Path(task.result), installer_upgrade_args(app_root), status)

    task.finished.connect(finished)
    window.advanced.update_download = task
    task.start()


def _install_local_update(window, status: QLabel):
    from updates import prepare_local_update
    chosen, _ = QFileDialog.getOpenFileName(
        window.advanced or window,
        tr('업데이트 파일 선택'),
        str(window.directory),
        tr('업데이트 파일 (*setup*.exe *.exe *.zip);;모든 파일 (*)'),
    )
    if not chosen:
        return
    try:
        result = prepare_local_update(Path(chosen))
    except (ValueError, OSError) as error:
        status.setText(str(error))
        QMessageBox.warning(window.advanced or window, tr('업데이트 실패'), str(error))
        return

    if result["mode"] == "installer":
        answer = QMessageBox.question(
            window.advanced or window,
            tr('인플레이스 업데이트 설치'),
            tr('현재 작업 상태를 저장하고 선택한 설치 파일로 덮어쓰기 업데이트를 진행할까요?\n(사용자 데이터·프로필·클립은 그대로 유지됩니다)'),
        )
        if answer == QMessageBox.StandardButton.Yes:
            _launch_installer_and_close(window, result["path"], result["args"], status)
    elif result["mode"] == "zip":
        status.setText(tr('소스 파일 {count}개를 업데이트했습니다. 재시작하면 적용됩니다.', count=result["updated_files"]))
        answer = QMessageBox.question(
            window.advanced or window,
            tr('업데이트 완료'),
            tr('파일 {count}개를 업데이트했습니다. 지금 앱을 다시 시작할까요?', count=result["updated_files"]),
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                window.save_recovery()
            except Exception:
                pass
            arguments = sys.argv[1:] if getattr(sys, "frozen", False) else sys.orig_argv[1:]
            started, _ = QProcess.startDetached(sys.executable, arguments, os.getcwd())
            if started:
                if window.advanced:
                    window.advanced.close()
                window.close()


def _check_updates(window, status, check):
    from tasks import Task
    from updates import VERSION, RELEASES_PAGE, is_newer, latest_release_info
    check.setEnabled(False)
    status.setText(tr('새 버전을 확인하는 중입니다…'))
    task = Task(lambda cancel, report: latest_release_info(), window.advanced)

    def finished():
        check.setEnabled(True)
        if task.error:
            status.setText(tr('새 버전을 확인하지 못했습니다. 인터넷 연결을 확인해 주세요.'))
        elif task.result is None:
            status.setText(tr('아직 공개된 버전이 없습니다. 현재 버전 {name}', name=VERSION))
        elif is_newer(task.result.get("tag", "")):
            tag = task.result["tag"]
            status.setText(tr('새 버전 {name}이 있습니다.', name=tag))
            if task.result.get("installer_url"):
                dialog = QMessageBox(window.advanced)
                dialog.setWindowTitle(tr('앱 버전'))
                dialog.setText(tr('새 버전 {name}이 있습니다. 어떻게 업데이트할까요?', name=tag))
                auto_btn = dialog.addButton(tr('자동 다운로드 및 업데이트 설치'), QMessageBox.ButtonRole.AcceptRole)
                web_btn = dialog.addButton(tr('릴리스 페이지 열기'), QMessageBox.ButtonRole.ActionRole)
                dialog.addButton(tr('취소'), QMessageBox.ButtonRole.RejectRole)
                dialog.exec()
                if dialog.clickedButton() == auto_btn:
                    _download_and_apply_release(window, task.result, status, check)
                elif dialog.clickedButton() == web_btn:
                    QDesktopServices.openUrl(QUrl(task.result.get("url") or RELEASES_PAGE))
            else:
                answer = QMessageBox.question(window.advanced, tr('앱 버전'),
                                              tr('새 버전 {name}이 있습니다. 받는 곳을 열까요?', name=tag))
                if answer == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl(task.result.get("url") or RELEASES_PAGE))
        else:
            status.setText(tr('최신 버전입니다. 현재 버전 {name}', name=VERSION))

    task.finished.connect(finished)
    # Hold the thread on the dialog so Qt does not delete it while it runs.
    window.advanced.update_check = task
    task.start()


def _report_problem(window):
    from updates import report_url
    if not QDesktopServices.openUrl(QUrl(report_url())):
        QMessageBox.information(window.advanced, tr('문제 신고'),
                                tr('브라우저를 열지 못했습니다. 저장소의 Issues 페이지에서 신고해 주세요.'))
