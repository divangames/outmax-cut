"""Windows tray notifications, using the WinForms runtime already owned by WebView2."""
import logging
import os


class TrayNotifications:
    def __init__(self, icon_path):
        self.icon_path = str(icon_path)
        self.tray = None

    def notify(self, window, title, message, error=False):
        if os.name != "nt" or window is None or window.native is None:
            return
        try:
            from System import Action
            from System.Drawing import Icon
            from System.Windows.Forms import NotifyIcon, FormWindowState, ToolTipIcon

            def show():
                try:
                    form = window.native
                    if form.IsDisposed or form.WindowState != FormWindowState.Minimized:
                        return
                    if self.tray is None:
                        self.tray = NotifyIcon()
                        self.tray.Icon = Icon(self.icon_path)
                        self.tray.Text = "OUTMAX Cut"
                        def restore(*_):
                            form.WindowState = FormWindowState.Normal
                            form.Show()
                            form.Activate()
                            self.tray.Visible = False
                        self.tray.BalloonTipClicked += restore
                        self.tray.DoubleClick += restore
                        def dispose(*_):
                            self.tray.Visible = False
                            self.tray.Icon.Dispose()
                            self.tray.Dispose()
                        form.FormClosed += dispose
                    self.tray.Visible = True
                    self.tray.ShowBalloonTip(10000, title[:63], message[:255],
                                            ToolTipIcon.Warning if error else ToolTipIcon.Info)
                except Exception:
                    logging.exception("Tray notification failed")
            window.native.BeginInvoke(Action(show))
        except Exception:
            # Notification delivery must never change the result of an export.
            logging.exception("Could not dispatch tray notification")
