"""
Утилиты для работы с метаданными клиентских устройств и User-Agent.
"""

def parse_device_name(user_agent: str | None = None, client_device: str | None = None) -> str:
    """Формирование понятного имени устройства из заголовка User-Agent или клиентского параметра."""
    if client_device and client_device.strip():
        return client_device.strip()[:150]
    if not user_agent:
        return "Неизвестное устройство"

    ua = user_agent.lower()
    os_name = "Устройство"
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "windows" in ua:
        os_name = "Windows"
    elif "linux" in ua:
        os_name = "Linux"

    browser = "Браузер"
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"

    return f"{browser} ({os_name})"
