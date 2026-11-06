"""OUTMAX-owned per-user Explorer submenu. No global file associations changed."""
from pathlib import Path

SCOPES=['Directory','Directory\\Background']+[f'SystemFileAssociations\\{ext}' for ext in ('.mp4','.mov','.m4v','.mkv','.avi','.webm')]
ACTIONS=[('add','Добавить в текущую очередь'),('new','Создать новый пакет'),('review','Открыть и проверить пары'),('quick','Быстрый экспорт — последние настройки'),('new-only','Экспортировать только новые товары'),('check','Проверить исходники'),('resume','Продолжить незавершённый пакет'),('results','Открыть папку результатов'),('settings','Настройки OUTMAX Cut')]


def menu_entries(presets, files=False):
    entries=list(ACTIONS)
    if files:entries[6:6]=[('model','Назначить видео моделью'),('hands','Назначить видео руками')]
    if presets:entries[4:4]=[('presets','Экспорт по пресету')]
    return entries


def register_menu(executable, presets):
    import winreg
    executable=str(Path(executable).resolve())
    def put(path,values):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:
            for name,value in values.items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
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
    for scope in SCOPES:
        root='Software\\Classes\\'+scope+'\\shell\\OutmaxCut'
        remove(root+'\\command');remove(root+'\\shell')
        put(root,{'':'OUTMAX Cut','MUIVerb':'OUTMAX Cut','SubCommands':'','Icon':f'"{executable}",0'})
        for index,(action,label) in enumerate(menu_entries(presets,scope.startswith('SystemFileAssociations'))):
            branch=root+f'\\shell\\{index:03d}'
            put(branch,{'MUIVerb':label,'MultiSelectModel':'Player'})
            argument='%V' if 'Background' in scope else '%1'
            if action=='presets':
                put(branch,{'SubCommands':''})
                for offset,preset in enumerate(presets):
                    child=branch+f'\\shell\\{offset:03d}';put(child,{'MUIVerb':preset['name'],'MultiSelectModel':'Player'})
                    put(child+'\\command',{'':f'"{executable}" --shell-action preset --preset {preset["id"]} --open "{argument}"'})
                continue
            arguments='--shell-action '+action
            put(branch+'\\command',{'':f'"{executable}" {arguments} --open "{argument}"'})
    import ctypes
    ctypes.windll.shell32.SHChangeNotify(0x08000000,0,None,None)
