#Requires AutoHotkey v2.0
#SingleInstance Force

F3:: {
    ; Toggle mute state
    SoundSetMute(-1)  ; -1 toggles the current state

    ; Get current mute state and show notification
    isMuted := SoundGetMute()
    if (isMuted)
        TrayTip('Audio Muted', 'System audio is now muted', 1)
    else
        TrayTip('Audio Unmuted', 'System audio is now unmuted', 1)
}