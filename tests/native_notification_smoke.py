"""Exercise the real WinForms tray and its click handler in a temporary WebView window."""
from pathlib import Path
import sys
import threading
import faulthandler
faulthandler.dump_traceback_later(25)

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from notifications import TrayNotifications

window=webview.create_window("Проверка уведомлений OUTMAX",html="<p>Проверка завершится автоматически.</p>",width=400,height=200)
minimized=threading.Event()
window.events.minimized += lambda: minimized.set()
notifier=TrayNotifications(Path(__file__).resolve().parents[1]/"assets/icon.ico")
errors=[]


def test():
    try:
        print("Native window worker started",flush=True)
        from System import Action, Array, Object, EventArgs
        from System.Reflection import BindingFlags
        from System.Windows.Forms import FormWindowState
        assert window.events.loaded.wait(20), "WebView2 did not finish loading"
        window.minimize()
        print("Minimize requested",flush=True)
        assert minimized.wait(5), "Window did not minimize"
        notifier.notify(window,"Проверка OUTMAX завершена","Нажатие возвращает окно приложения.")
        print("Notification dispatched",flush=True)
        checked=threading.Event()
        def inspect():
            try:
                assert notifier.tray is not None and notifier.tray.Visible
                # Invoke exactly the WinForms event raised by clicking the banner.
                method=notifier.tray.GetType().GetMethod("OnBalloonTipClicked",BindingFlags.NonPublic|BindingFlags.Instance)
                args=[] if len(method.GetParameters())==0 else [EventArgs.Empty]
                method.Invoke(notifier.tray,Array[Object](args))
                assert window.native.WindowState==FormWindowState.Normal
                assert not notifier.tray.Visible
            except Exception as exc:
                errors.append(exc)
            finally:
                checked.set()
        window.native.BeginInvoke(Action(inspect))
        assert checked.wait(5), "Notification callback timed out"
        print("Notification inspected",flush=True)
        # Folder notifications must leave the editor hidden. A subsequent tray
        # refresh must not replace the completion banner's captured action.
        opened=threading.Event();report=lambda:None
        notifier.background(window,report,lambda:None,lambda:None)
        window.hide()
        notifier.notify(window,"Автосборка завершена","Нажмите, чтобы открыть готовые ролики.",
                        force=True,on_click=opened.set,activate_on_click=False)
        notifier.background(window,report,lambda:None,lambda:None)
        checked.clear()
        def inspect_folder():
            try:
                assert not window.native.Visible
                assert notifier.tray_action is report
                method=notifier.tray.GetType().GetMethod("OnBalloonTipClicked",BindingFlags.NonPublic|BindingFlags.Instance)
                args=[] if len(method.GetParameters())==0 else [EventArgs.Empty]
                method.Invoke(notifier.tray,Array[Object](args))
                assert not window.native.Visible, "Folder banner restored the editor"
                assert notifier.tray.Visible, "Resident tray disappeared"
            except Exception as exc:errors.append(exc)
            finally:checked.set()
        window.native.BeginInvoke(Action(inspect_folder))
        assert checked.wait(5), "Folder banner inspection timed out"
        assert opened.wait(5), "Folder callback did not run"
        print("Folder notification inspected",flush=True)
    except Exception as exc:
        errors.append(exc)
    finally:
        print("Closing native test",errors,flush=True)
        window.destroy()


webview.start(test,gui="edgechromium")
faulthandler.cancel_dump_traceback_later()
if errors:
    raise RuntimeError(str(errors))
print("PASS: normal banner restores editor; folder banner runs captured action without restoring editor; tray disposed on close")
