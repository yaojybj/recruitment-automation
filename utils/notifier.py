"""桌面通知 - 关键节点弹窗提醒"""

import platform
import subprocess
from utils.logger import get_logger


def notify(title: str, message: str, level: str = "info"):
    """
    发送桌面通知。
    level: info / warning / error
    """
    logger = get_logger()
    logger.info(f"[通知] {title}: {message}")

    system = platform.system()
    try:
        if system == "Darwin":
            sound = 'sound name "Glass"' if level == "error" else ""
            script = (
                f'display notification "{message}" '
                f'with title "{title}" {sound}'
            )
            subprocess.run(["osascript", "-e", script],
                           capture_output=True, timeout=5)

        elif system == "Windows":
            _windows_toast(title, message)

        elif system == "Linux":
            icon = {
                "info": "dialog-information",
                "warning": "dialog-warning",
                "error": "dialog-error"
            }.get(level, "dialog-information")
            subprocess.run(
                ["notify-send", "-i", icon, title, message],
                capture_output=True, timeout=5
            )
    except Exception as e:
        logger.warning(f"桌面通知发送失败: {e}")


def _windows_toast(title: str, message: str):
    """Windows 10+ toast notification via PowerShell"""
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName('text')
    $textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode('{message}')) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('招聘自动化').Show($toast)
    """
    subprocess.run(["powershell", "-Command", ps_script],
                   capture_output=True, timeout=10)
