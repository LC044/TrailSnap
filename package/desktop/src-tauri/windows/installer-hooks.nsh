; Capture at include time: __FILEDIR__ inside a macro refers to the generated
; installer directory rather than this hooks directory.
!define TRAILSNAP_HOOK_DIR "${__FILEDIR__}"

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
  !insertmacro TRAILSNAP_STOP_INSTALLED_PROCESSES
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro TRAILSNAP_STOP_INSTALLED_PROCESSES
!macroend
