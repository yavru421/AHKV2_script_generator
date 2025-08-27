; Test AHK v2 script
#Requires AutoHotkey v2.0
#SingleInstance Force

; Simple hotkey
^j:: MsgBox "Hello World"

; Volume control
^!WheelUp:: Send "{Volume_Up}"
^!WheelDown:: Send "{Volume_Down}"

; Function
ShowTime() {
    current_time := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    MsgBox current_time
}

F1:: ShowTime()