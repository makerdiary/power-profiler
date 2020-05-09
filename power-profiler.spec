# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['power_profiler\\power_profiler.py'],
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['tcl', 'tk', '_tkinter', 'tkinter', 'Tkinter', 'shiboken2', 'lib2to3', 'ssl', 'bz2', 'lzma', 'curses'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
excluded_binaries = ['libGLESv2.dll',
                    'Qt5Network.dll',
                    'Qt5Qml.dll',
                    'Qt5Quick.dll',
                    'Qt5WebSockets.dll',
                    'opengl32sw.dll',
                    'Qt5DBus.dll',
                    'Qt5OpenGL.dll',
                    'Qt5QmlModels.dll',
                    'Qt5Test.dll',
                    'Qt5Svg.dll',
                    'libcrypto-1_1.dll',
                    'd3dcompiler_47.dll',
                    'libEGL.dll']
a.binaries = TOC([x for x in a.binaries if x[0] not in excluded_binaries])
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='power-profiler',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False )
