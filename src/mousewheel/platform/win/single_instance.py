"""单实例：命名互斥体 + 本机 socket 唤醒已运行实例。

第二个实例启动时不应该再挂一套钩子（会双份弹轮盘），而是通知已有实例
把设置窗口叫出来，然后自己退出。
"""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .winapi import kernel32, ERROR_ALREADY_EXISTS

__all__ = ["SingleInstance", "SERVER_NAME"]

SERVER_NAME = "MouseWheel.DSH.SingleInstance.v1"

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool


class SingleInstance(QObject):
    """IPC 服务端。收到 ``show`` 之类消息时发 :attr:`message` 信号。"""

    message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mutex = None
        self._server: QLocalServer | None = None

    # ---- 互斥体 ----------------------------------------------------------

    def acquire_mutex(self) -> bool:
        """返回 True 表示本进程是唯一实例。"""
        handle = kernel32.CreateMutexW(None, False, f"Local\\{SERVER_NAME}.mutex")
        if not handle:
            return True  # 建不出来就当作唯一实例，别阻止用户使用
        self._mutex = handle
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    # ---- 服务端 ----------------------------------------------------------

    def start_server(self) -> bool:
        QLocalServer.removeServer(SERVER_NAME)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(SERVER_NAME):
            return False
        self._server.newConnection.connect(self._on_new_connection)
        return True

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda c=conn: self._read(c))
        conn.disconnected.connect(conn.deleteLater)

    def _read(self, conn: QLocalSocket) -> None:
        data = bytes(conn.readAll()).decode("utf-8", "ignore").strip()
        if data:
            self.message.emit(data)
        conn.disconnectFromServer()

    # ---- 客户端 ----------------------------------------------------------

    @staticmethod
    def notify_existing(payload: str = "show", timeout_ms: int = 800) -> bool:
        """给已运行实例发消息。成功返回 True。"""
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        if not sock.waitForConnected(timeout_ms):
            return False
        sock.write(payload.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        return True

    # ---- 清理 ------------------------------------------------------------

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._mutex:
            kernel32.CloseHandle(self._mutex)
            self._mutex = None
