"""Windows registration contracts, including Explorer's open registry handles."""
import os
from pathlib import Path
import unittest
import uuid

from explorer_menu import register_menu, SCOPES

if os.name == 'nt':
    import winreg


@unittest.skipUnless(os.name == 'nt', 'Windows registry integration')
class ExplorerRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.root=r'Software\OutmaxCutTests'+chr(92)+uuid.uuid4().hex
        self.classes=self.root+r'\Classes'
        self.old=Path('C:/OUTMAX test/old/OUTMAX-Cut.exe')
        self.new=Path('C:/OUTMAX test/new/OUTMAX-Cut.exe')

    def tearDown(self):
        def erase(path):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
                    children=[winreg.EnumKey(key,i) for i in range(winreg.QueryInfoKey(key)[0])]
                for child in children:erase(path+'\\'+child)
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
            except FileNotFoundError:pass
        erase(self.root)

    def path(self,scope,verb='OutmaxCutAuto'):
        return self.classes+'\\'+scope+'\\shell\\'+verb

    def value(self,path,name=''):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
            return winreg.QueryValueEx(key,name)[0]

    def test_file_folder_and_multiple_selection_are_registered_without_changing_default_open(self):
        register_menu(self.old,[],classes_root=self.classes,notify=False)
        self.assertIn('Folder',SCOPES)
        for scope in SCOPES:
            direct=self.path(scope)
            self.assertEqual(self.value(direct,'MultiSelectModel'),'Player')
            self.assertEqual(self.value(direct,'NeverDefault'),'')
            self.assertEqual(self.value(self.path(scope,'OutmaxCut'),'NeverDefault'),'')
            self.assertEqual(self.value(self.path(scope,'OutmaxCut')),'')
            self.assertIn('--shell-action auto --open',self.value(direct+r'\command'))
        installer=(Path(__file__).resolve().parents[1]/'tools/installer.iss').read_text(encoding='utf-8')
        for scope in SCOPES:
            for verb in ('OutmaxCut','OutmaxCutAuto'):
                self.assertIn(f'Software\\Classes\\{scope}\\shell\\{verb}"',installer)

    def test_update_keeps_explorers_live_command_handles_valid(self):
        register_menu(self.old,[],classes_root=self.classes,notify=False)
        direct=self.path('Directory')
        branch=self.path('Directory','OutmaxCut')+r'\shell\000\command'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,branch) as command,winreg.OpenKey(winreg.HKEY_CURRENT_USER,direct,0,winreg.KEY_ALL_ACCESS) as auto:
            winreg.SetValueEx(auto,'Position',0,winreg.REG_SZ,'Top')
            register_menu(self.new,[],classes_root=self.classes,notify=False)
            self.assertIn(str(self.new),winreg.QueryValueEx(command,'')[0])
            self.assertEqual(winreg.QueryValueEx(auto,'NeverDefault')[0],'')
            with self.assertRaises(FileNotFoundError):winreg.QueryValueEx(auto,'Position')

    def test_presets_removed_without_leaving_old_commands_or_deleting_live_preset_keys(self):
        presets=[dict(id='first',name='Сайт'),dict(id='second',name='Другой')]
        register_menu(self.old,presets,classes_root=self.classes,notify=False)
        parent=self.path('Directory','OutmaxCut')+r'\shell\004\shell'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,parent+r'\000\command') as command:
            register_menu(self.new,presets[:1],classes_root=self.classes,notify=False)
            self.assertIn('--preset first',winreg.QueryValueEx(command,'')[0])
            self.assertIn(str(self.new),winreg.QueryValueEx(command,'')[0])
            with self.assertRaises(FileNotFoundError):winreg.OpenKey(winreg.HKEY_CURRENT_USER,parent+r'\001')
        register_menu(self.new,[],classes_root=self.classes,notify=False)
        with self.assertRaises(FileNotFoundError):winreg.OpenKey(winreg.HKEY_CURRENT_USER,parent)
        self.assertIn('--shell-action quick',self.value(self.path('Directory','OutmaxCut')+r'\shell\004\command'))


if __name__=='__main__':unittest.main()
