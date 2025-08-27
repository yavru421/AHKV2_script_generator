#Requires AutoHotkey v2.0
#SingleInstance Force

F3:: {
    SoundSetMute(-1)  ; Toggle mute
    if (SoundGetMute()) {
        TrayTip("Volume", "Muted")
    } else {
        TrayTip("Volume", "Unmuted")
    }
}