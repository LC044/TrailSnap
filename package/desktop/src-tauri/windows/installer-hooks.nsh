; Capture at include time: __FILEDIR__ inside a macro refers to the generated
; installer directory rather than this hooks directory.
!define TRAILSNAP_HOOK_DIR "${__FILEDIR__}"
Var TrailSnapInstanceTag
Var TrailSnapInstanceName
Var TrailSnapShortTag

!macro TRAILSNAP_INSTANCE_IDENTITY
  InitPluginsDir
  File /oname=$PLUGINSDIR\trailsnap-stop-processes.ps1 "${TRAILSNAP_HOOK_DIR}\stop-installed-processes.ps1"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\trailsnap-stop-processes.ps1" -InstallDirectory "$INSTDIR" -IdentityOnly'
  Pop $0
  Pop $TrailSnapInstanceTag
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "无法识别安装目录，请选择可写的独立文件夹。" /SD IDOK
    Abort
  ${EndIf}
  StrCpy $TrailSnapInstanceTag $TrailSnapInstanceTag 64
  StrCpy $TrailSnapShortTag $TrailSnapInstanceTag 8
  ${GetFileName} "$INSTDIR" $TrailSnapInstanceName
!macroend

!macro TRAILSNAP_STOP_INSTALLED_PROCESSES
  InitPluginsDir
  File /oname=$PLUGINSDIR\trailsnap-stop-processes.ps1 "${TRAILSNAP_HOOK_DIR}\stop-installed-processes.ps1"
  nsExec::ExecToStack /TIMEOUT=20000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\trailsnap-stop-processes.ps1" -InstallDirectory "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    DetailPrint "$1"
    MessageBox MB_OK|MB_ICONSTOP "Unable to close TrailSnap. Close the app and run setup again." /SD IDOK
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro TRAILSNAP_INSTANCE_IDENTITY
  !insertmacro TRAILSNAP_STOP_INSTALLED_PROCESSES
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro TRAILSNAP_INSTANCE_IDENTITY
  !insertmacro TRAILSNAP_STOP_INSTALLED_PROCESSES
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Both distribution formats use the exact same program/data layout. The
  ; helper stages immutable program files and never replaces instance.json.
  nsExec::ExecToStack '"$INSTDIR\server\trailsnap-server.exe" --install-layout "$INSTDIR" "${VERSION}"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    DetailPrint "$1"
    MessageBox MB_OK|MB_ICONSTOP "安装目录初始化失败。请选择可写目录重试，原有 userdata 不会被覆盖。$\r$\n$1" /SD IDOK
    Abort
  ${EndIf}
  ; Tauri's existing shortcuts/updater launch this filename. Keep it as a
  ; launcher alias; the actual shell now lives in app/<build-id>.
  CopyFiles /SILENT "$INSTDIR\portable-launcher.exe" "$INSTDIR\trailsnap-desktop.exe"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  InitPluginsDir
  File /oname=$PLUGINSDIR\trailsnap-remove-programs.ps1 "${TRAILSNAP_HOOK_DIR}\remove-instance-programs.ps1"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\trailsnap-remove-programs.ps1" -InstallDirectory "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    DetailPrint "$1"
    MessageBox MB_OK|MB_ICONINFORMATION "部分程序文件已保留，请检查安装目录。图库和配置未删除。$\r$\n$1" /SD IDOK
  ${EndIf}
!macroend
