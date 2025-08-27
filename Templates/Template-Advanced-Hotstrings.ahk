#Requires AutoHotkey v2.0
#SingleInstance Force
#Persistent
MsgBox("Template-Advanced-Hotstrings.ahk is running.")

; ======================================================================================================================
; TEMPLATE: Advanced Text Expander (Hotstrings)
; DESCRIPTION: Define simple abbreviations that expand into larger blocks of text.
;              This example uses a Map object to store the hotstrings for easy management.
; ======================================================================================================================

; --- Data Structure for Hotstrings ---
; Using a Map is a clean way to manage a large number of hotstrings.
; --- Dynamic Hotstring Creation ---
; Loop through the Map and create each hotstring programmatically.
; --- Inform the user ---
; --- Hotkey to exit this script ---
#Requires AutoHotkey v2.0
#SingleInstance Force
#Persistent

::btw::by the way
::sig::Sincerely,`nJohn Doe`nSoftware Developer
::adr::123 Main Street`nAnytown, USA 12345
::##::% FormatTime(,"yyyy-MM-dd")

MsgBox("Hotstrings are active. Type 'btw', 'sig', 'adr', or '##' in any text field.")

F4::ExitApp
