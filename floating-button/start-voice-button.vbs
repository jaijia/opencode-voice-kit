' 启动语音悬浮按钮（无控制台窗口）
' 用法：双击本文件，或在命令行运行 wscript start-voice-button.vbs
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
py = scriptDir & "\voice_button.py"
sh.Run "pythonw.exe """ & py & """", 0, False
