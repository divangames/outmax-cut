"""OUTMAX-owned per-user Explorer submenu. No global file associations changed."""
from pathlib import Path

SCOPES=['Folder','Directory','Directory\\Background']+[f'SystemFileAssociations\\{ext}' for ext in ('.mp4','.mov','.m4v','.mkv','.avi','.webm')]
ACTIONS=[('auto','Собрать автоматически'),('add','Добавить в текущую очередь'),('new','Создать новый пакет'),('review','Открыть и проверить пары'),('quick','Быстрый экспорт — последние настройки'),('new-only','Экспортировать только новые товары'),('check','Проверить исходники'),('resume','Продолжить незавершённый пакет'),('results','Открыть папку результатов'),('settings','Настройки OUTMAX Cut')]


def menu_entries(presets, files=False):
    entries=list(ACTIONS)
    if files:entries[6:6]=[('model','Назначить видео моделью'),('hands','Назначить видео руками')]
    if presets:entries[4:4]=[('presets','Экспорт по пресету')]
    return entries


def register_menu(executable, presets, *, classes_root=r'Software\Classes', notify=True):
    import winreg
    executable=str(Path(executable).resolve())
    def put(path,values):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:
            for name,value in values.items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    def discard_value(path,name):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_SET_VALUE) as key:
            try:winreg.DeleteValue(key,name)
            except FileNotFoundError:pass
    def remove(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|winreg.KEY_WRITE) as key:
                children=[]
                while True:
                    try:children.append(winreg.EnumKey(key,len(children)))
                    except OSError:break
            for child in children:remove(path+'\\'+child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError:pass
    def retain_children(path,names):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ) as key:
            children=[winreg.EnumKey(key,index) for index in range(winreg.QueryInfoKey(key)[0])]
        for child in children:
            if child not in names:remove(path+'\\'+child)
    for scope in SCOPES:
        direct=classes_root+'\\'+scope+'\\shell\\OutmaxCutAuto'
        argument='%V' if 'Background' in scope else '%1'
        put(direct,{'':'Собрать видео автоматически','MUIVerb':'Собрать видео автоматически','Icon':f'"{executable}",0','MultiSelectModel':'Player','NeverDefault':''})
        discard_value(direct,'Position')
        put(direct+'\\command',{'':f'"{executable}" --shell-action auto --open "{argument}"'})
        root=classes_root+'\\'+scope+'\\shell\\OutmaxCut'
        remove(root+'\\command')
        put(root,{'':'','MUIVerb':'OUTMAX Cut','SubCommands':'','Icon':f'"{executable}",0','MultiSelectModel':'Player','NeverDefault':''})
        # Explorer may keep these keys open. Update live commands in place so an
        # upgrade never leaves its cached submenu pointing at deleted keys.
        put(root+'\\shell',{})
        entries=menu_entries(presets,scope.startswith('SystemFileAssociations'))
        for index,(action,label) in enumerate(entries):
            branch=root+f'\\shell\\{index:03d}'
            put(branch,{'MUIVerb':label,'MultiSelectModel':'Player'})
            argument='%V' if 'Background' in scope else '%1'
            if action=='presets':
                remove(branch+'\\command')
                put(branch,{'SubCommands':''})
                put(branch+'\\shell',{})
                for offset,preset in enumerate(presets):
                    child=branch+f'\\shell\\{offset:03d}';put(child,{'MUIVerb':preset['name'],'MultiSelectModel':'Player'})
                    put(child+'\\command',{'':f'"{executable}" --shell-action preset --preset {preset["id"]} --open "{argument}"'})
                retain_children(branch+'\\shell',{f'{offset:03d}' for offset in range(len(presets))})
                continue
            discard_value(branch,'SubCommands');remove(branch+'\\shell')
            arguments='--shell-action '+action
            put(branch+'\\command',{'':f'"{executable}" {arguments} --open "{argument}"'})
        retain_children(root+'\\shell',{f'{index:03d}' for index in range(len(entries))})
    if notify:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000,0x1000,None,None)
