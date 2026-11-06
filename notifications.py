"""Windows notifications and a resident tray for background exports."""
import logging
import os
import threading


class TrayNotifications:
    def __init__(self,icon_path):
        self.icon_path=str(icon_path);self.tray=None;self.resident=False;self.click_action=None;self.editor_callback=None;self.last_notification=None

    def _dispatch(self,window,callback):
        if os.name!='nt' or window is None or window.native is None:return
        try:
            from System import Action
            def invoke():
                try:
                    if not window.native.IsDisposed:callback(window.native)
                except Exception:logging.exception('Tray operation failed')
            window.native.BeginInvoke(Action(invoke))
        except Exception:logging.exception('Could not dispatch tray operation')

    def _activate(self,form,callback=None):
        from System.Windows.Forms import FormWindowState
        form.WindowState=FormWindowState.Normal;form.Show();form.Activate()
        if not self.resident:self.tray.Visible=False
        callback=callback or (self.editor_callback if self.resident else None)
        if callback:threading.Thread(target=callback,daemon=True).start()

    def _ensure(self,form):
        if self.tray is not None:return
        from System.Drawing import Icon
        from System.Windows.Forms import NotifyIcon
        self.tray=NotifyIcon();self.tray.Icon=Icon(self.icon_path);self.tray.Text='OUTMAX Cut'
        self.tray.BalloonTipClicked+=lambda *_:self._activate(form,self.click_action)
        self.tray.DoubleClick+=lambda *_:self._activate(form,self.click_action if self.resident else None)
        def dispose(*_):
            self.tray.Visible=False;self.tray.Icon.Dispose();self.tray.Dispose()
        form.FormClosed+=dispose

    def background(self,window,open_report,open_folder,cancel,status='OUTMAX Cut · автосборка',exit_callback=None):
        def show(form):
            from System.Windows.Forms import ContextMenuStrip,ToolStripMenuItem
            self._ensure(form);self.resident=True;self.click_action=open_report
            if self.tray.ContextMenuStrip is None:
                menu=ContextMenuStrip()
                for title,callback,activate in [('Открыть редактор',None,True),('Автосборка: ход и результаты',open_report,True),('Открыть папку готовых роликов',open_folder,False),('Остановить автосборку',cancel,False),('Выход',exit_callback or window.destroy,False)]:
                    item=ToolStripMenuItem(title)
                    def clicked(*_,callback=callback,activate=activate):
                        if activate:self._activate(form,callback)
                        elif callback:threading.Thread(target=callback,daemon=True).start()
                    item.Click+=clicked;menu.Items.Add(item)
                self.tray.ContextMenuStrip=menu
            self.tray.Text=status[:63];self.tray.Visible=True
        self._dispatch(window,show)

    def notify(self,window,title,message,error=False,force=False,on_click=None):
        def show(form):
            from System.Windows.Forms import FormWindowState,ToolTipIcon
            if not force and form.Visible and form.WindowState!=FormWindowState.Minimized:return
            self._ensure(form)
            self.click_action=on_click
            self.tray.Visible=True
            self.tray.ShowBalloonTip(10000,title[:63],message[:255],ToolTipIcon.Warning if error else ToolTipIcon.Info)
            self.last_notification=dict(title=title,message=message,error=bool(error))
        self._dispatch(window,show)
