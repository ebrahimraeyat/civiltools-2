' ============================================================
'  civilTools - Standalone Bootstrapper
'  ============================================================
'  Double-click this file on any Windows PC to:
'    1. Choose an install folder (Browse dialog)
'    2. Clone the repository (or download as ZIP if Git missing)
'    3. Run install.bat which handles everything else
'
'  This file can be distributed independently (email, USB, etc.)
' ============================================================

Option Explicit

Dim objShell, objFSO
Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")

Const REPO_URL = "https://github.com/ebrahimraeyat/civiltools.git"
Const ZIP_URL  = "https://github.com/ebrahimraeyat/civiltools/archive/refs/heads/master.zip"
Const FOLDER   = "civiltools"

' --- Choose install location (Browse dialog with text field) -----------
Dim defaultPath
defaultPath = objShell.ExpandEnvironmentStrings("%USERPROFILE%") & "\Documents"

' Write a PowerShell script to a temp file that shows a WinForms dialog
Dim psTempFile
psTempFile = objShell.ExpandEnvironmentStrings("%TEMP%") & "\ct_folder_picker.ps1"

Dim psFile
Set psFile = objFSO.CreateTextFile(psTempFile, True)
psFile.WriteLine "Add-Type -AssemblyName System.Windows.Forms"
psFile.WriteLine "Add-Type -AssemblyName System.Drawing"
psFile.WriteLine "[System.Windows.Forms.Application]::EnableVisualStyles()"
psFile.WriteLine ""
psFile.WriteLine "$form = New-Object System.Windows.Forms.Form"
psFile.WriteLine "$form.Text = 'civilTools Installer'"
psFile.WriteLine "$form.Size = New-Object System.Drawing.Size(540, 200)"
psFile.WriteLine "$form.StartPosition = 'CenterScreen'"
psFile.WriteLine "$form.FormBorderStyle = 'FixedDialog'"
psFile.WriteLine "$form.MaximizeBox = $false"
psFile.WriteLine "$form.MinimizeBox = $false"
psFile.WriteLine "$form.TopMost = $true"
psFile.WriteLine ""
psFile.WriteLine "$lbl = New-Object System.Windows.Forms.Label"
psFile.WriteLine "$lbl.Text = 'Select the folder where civilTools will be installed:'"
psFile.WriteLine "$lbl.Location = New-Object System.Drawing.Point(12, 15)"
psFile.WriteLine "$lbl.AutoSize = $true"
psFile.WriteLine "$form.Controls.Add($lbl)"
psFile.WriteLine ""
psFile.WriteLine "$lbl2 = New-Object System.Windows.Forms.Label"
psFile.WriteLine "$lbl2.Text = '(A subfolder named ""civiltools"" will be created inside it)'"
psFile.WriteLine "$lbl2.Location = New-Object System.Drawing.Point(12, 38)"
psFile.WriteLine "$lbl2.AutoSize = $true"
psFile.WriteLine "$lbl2.ForeColor = [System.Drawing.Color]::Gray"
psFile.WriteLine "$form.Controls.Add($lbl2)"
psFile.WriteLine ""
psFile.WriteLine "$txt = New-Object System.Windows.Forms.TextBox"
psFile.WriteLine "$txt.Text = '" & defaultPath & "'"
psFile.WriteLine "$txt.Location = New-Object System.Drawing.Point(12, 65)"
psFile.WriteLine "$txt.Size = New-Object System.Drawing.Size(410, 24)"
psFile.WriteLine "$form.Controls.Add($txt)"
psFile.WriteLine ""
psFile.WriteLine "$btnBrowse = New-Object System.Windows.Forms.Button"
psFile.WriteLine "$btnBrowse.Text = 'Browse...'"
psFile.WriteLine "$btnBrowse.Location = New-Object System.Drawing.Point(430, 63)"
psFile.WriteLine "$btnBrowse.Size = New-Object System.Drawing.Size(80, 27)"
psFile.WriteLine "$btnBrowse.Add_Click({"
psFile.WriteLine "  $fbd = New-Object System.Windows.Forms.FolderBrowserDialog"
psFile.WriteLine "  $fbd.Description = 'Select installation folder'"
psFile.WriteLine "  $fbd.SelectedPath = $txt.Text"
psFile.WriteLine "  $fbd.ShowNewFolderButton = $true"
psFile.WriteLine "  if ($fbd.ShowDialog() -eq 'OK') { $txt.Text = $fbd.SelectedPath }"
psFile.WriteLine "})"
psFile.WriteLine "$form.Controls.Add($btnBrowse)"
psFile.WriteLine ""
psFile.WriteLine "$btnOK = New-Object System.Windows.Forms.Button"
psFile.WriteLine "$btnOK.Text = 'Install'"
psFile.WriteLine "$btnOK.Location = New-Object System.Drawing.Point(270, 110)"
psFile.WriteLine "$btnOK.Size = New-Object System.Drawing.Size(100, 30)"
psFile.WriteLine "$btnOK.DialogResult = [System.Windows.Forms.DialogResult]::OK"
psFile.WriteLine "$form.Controls.Add($btnOK)"
psFile.WriteLine "$form.AcceptButton = $btnOK"
psFile.WriteLine ""
psFile.WriteLine "$btnCancel = New-Object System.Windows.Forms.Button"
psFile.WriteLine "$btnCancel.Text = 'Cancel'"
psFile.WriteLine "$btnCancel.Location = New-Object System.Drawing.Point(380, 110)"
psFile.WriteLine "$btnCancel.Size = New-Object System.Drawing.Size(100, 30)"
psFile.WriteLine "$btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel"
psFile.WriteLine "$form.Controls.Add($btnCancel)"
psFile.WriteLine "$form.CancelButton = $btnCancel"
psFile.WriteLine ""
psFile.WriteLine "$result = $form.ShowDialog()"
psFile.WriteLine "if ($result -eq 'OK') { Write-Host $txt.Text } else { Write-Host '::CANCEL::' }"
psFile.Close
Set psFile = Nothing

Dim psPath
psPath = objShell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"

Dim installDir
Dim psExec
Set psExec = objShell.Exec("""" & psPath & """ -NoProfile -ExecutionPolicy Bypass -File """ & psTempFile & """")
installDir = psExec.StdOut.ReadAll
Set psExec = Nothing

' Strip all whitespace (spaces, CR, LF) from both ends
installDir = Replace(installDir, vbCrLf, "")
installDir = Replace(installDir, vbCr, "")
installDir = Replace(installDir, vbLf, "")
installDir = Trim(installDir)

' Clean up temp file
On Error Resume Next
objFSO.DeleteFile psTempFile, True
On Error GoTo 0

' Handle cancel or empty
If installDir = "" Or installDir = "::CANCEL::" Then WScript.Quit

If Not objFSO.FolderExists(installDir) Then
    MsgBox "The folder """ & installDir & """ does not exist.", vbExclamation, "Error"
    WScript.Quit
End If

Dim targetPath
targetPath = installDir & "\" & FOLDER

If objFSO.FolderExists(targetPath) Then
    Dim overwrite
    overwrite = MsgBox( _
        "The folder """ & targetPath & """ already exists." & vbCrLf & _
        "Would you like to update it instead of re-downloading?", _
        vbYesNoCancel + vbQuestion, "Folder Exists")
    If overwrite = vbCancel Then WScript.Quit
    If overwrite = vbYes Then
        Dim updateBat
        updateBat = targetPath & "\update.bat"
        If objFSO.FileExists(updateBat) Then
            objShell.CurrentDirectory = targetPath
            objShell.Run "cmd /k """ & updateBat & """", 1, False
        Else
            MsgBox "update.bat not found in " & targetPath, vbExclamation, "Error"
        End If
        WScript.Quit
    End If
    ' vbNo = re-download, remove old folder
    objFSO.DeleteFolder targetPath, True
End If

' --- Try cloning with Git ---------------------------------------------
Dim hasGit
hasGit = False
On Error Resume Next
Dim gitTestResult
gitTestResult = objShell.Run("cmd /c git --version", 0, True)
If Err.Number = 0 And gitTestResult = 0 Then hasGit = True
Err.Clear
On Error GoTo 0

Dim cloneOK
cloneOK = False

If hasGit Then
    Dim cloneCmd
    cloneCmd = "cmd /c cd /d """ & installDir & """ && git clone --depth=1 " & REPO_URL
    Dim cloneResult
    cloneResult = objShell.Run(cloneCmd, 1, True)
    If cloneResult = 0 And objFSO.FolderExists(targetPath) Then
        cloneOK = True
    End If
End If

' --- Fallback: download ZIP --------------------------------------------
If Not cloneOK Then
    Dim zipPath
    zipPath = objShell.ExpandEnvironmentStrings("%TEMP%") & "\civiltools.zip"

    Dim dlMsg
    dlMsg = "Downloading civilTools as ZIP ..."
    If Not hasGit Then
        dlMsg = "Git not found. " & dlMsg & vbCrLf & _
                "(Git will be installed automatically during setup)"
    End If

    Dim dlResult
    dlResult = MsgBox(dlMsg & vbCrLf & vbCrLf & "Click OK to continue.", _
        vbOKCancel + vbInformation, "Downloading")
    If dlResult = vbCancel Then WScript.Quit

    ' Download using PowerShell
    Dim psDownload
    psDownload = """" & psPath & """ -NoProfile -Command ""& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '" & ZIP_URL & "' -OutFile '" & zipPath & "' }"""
    objShell.Run psDownload, 0, True

    If Not objFSO.FileExists(zipPath) Then
        MsgBox "Download failed. Please check your internet connection.", vbCritical, "Error"
        WScript.Quit
    End If

    ' Extract ZIP using PowerShell
    Dim extractDir
    extractDir = objShell.ExpandEnvironmentStrings("%TEMP%") & "\civiltools-extract"
    If objFSO.FolderExists(extractDir) Then objFSO.DeleteFolder extractDir, True

    Dim psExtract
    psExtract = """" & psPath & """ -NoProfile -Command ""Expand-Archive -Path '" & zipPath & _
        "' -DestinationPath '" & extractDir & "' -Force"""
    objShell.Run psExtract, 0, True

    ' The ZIP extracts as civiltools-master or similar
    Dim subFolder, f
    For Each f In objFSO.GetFolder(extractDir).SubFolders
        subFolder = f.Path
        Exit For
    Next

    If subFolder = "" Or Not objFSO.FolderExists(subFolder) Then
        MsgBox "Failed to extract the downloaded file.", vbCritical, "Error"
        WScript.Quit
    End If

    ' Move to target
    objFSO.MoveFolder subFolder, targetPath

    ' Cleanup
    On Error Resume Next
    objFSO.DeleteFile zipPath, True
    objFSO.DeleteFolder extractDir, True
    On Error GoTo 0
End If

' --- Run install.bat ---------------------------------------------------
Dim installBat
installBat = targetPath & "\install.bat"

If Not objFSO.FileExists(installBat) Then
    MsgBox "install.bat not found in " & targetPath & vbCrLf & _
           "The download may be incomplete.", vbCritical, "Error"
    WScript.Quit
End If

MsgBox "Download complete!" & vbCrLf & vbCrLf & _
    "Click OK to start the automated setup." & vbCrLf & _
    "A terminal window will open - this is normal.", _
    vbInformation, "civilTools"

objShell.CurrentDirectory = targetPath
objShell.Run "cmd /k """ & installBat & """", 1, False

' Done
Set objFSO   = Nothing
Set objShell = Nothing
