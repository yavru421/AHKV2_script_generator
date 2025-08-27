#Requires AutoHotkey v2.0
#SingleInstance Force

F3::
{
MsgBox("Hello World")
Send({Escape})
SoundSetVolume(+1)
}
