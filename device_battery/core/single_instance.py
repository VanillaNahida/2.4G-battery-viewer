# -*- coding: utf-8 -*-
"""single_instance.py —— 单实例（QLocalServer 版）

替代旧版用「窗口消息 + PID 文件 + 僵尸进程清理」的做法：
Qt 自带的本地 socket 更简单，也不会留下"占着锁却已经没窗口"的僵尸进程。

第二个实例连上来发一条消息（"show" 显示主窗口 / "quit" 退出），然后自己结束。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "device_battery_single"


def send_to_running(message: str, timeout_ms: int = 500) -> bool:
    """给正在运行的实例发一条消息；没有实例在跑返回 False。"""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(message.encode("utf-8"))
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


def is_running(timeout_ms: int = 300) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    ok = sock.waitForConnected(timeout_ms)
    sock.disconnectFromServer()
    return bool(ok)


class SingleInstance(QObject):
    """管理单实例锁。"""

    message_received = pyqtSignal(str)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._server: Optional[QLocalServer] = None

    def try_lock(self, timeout_ms: int = 300) -> bool:
        """返回 True 表示本进程是唯一实例（已开始监听）。"""
        if send_to_running("show", timeout_ms):
            return False

        QLocalServer.removeServer(SERVER_NAME)   # 清掉可能残留的 socket
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        return bool(self._server.listen(SERVER_NAME))

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._on_ready(conn))
        conn.disconnected.connect(conn.deleteLater)

    def _on_ready(self, conn: QLocalSocket) -> None:
        data = bytes(conn.readAll()).decode("utf-8", errors="ignore").strip()
        if data:
            self.message_received.emit(data)
