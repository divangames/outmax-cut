# OUTMAX Cut

## Platform
Windows desktop application, distributed with a Windows installer (confirmed by user).

## Users and workflow
User drops two product clips: Model (feet) and Hands. App makes a square edited MP4 using the supplied reference's timing, transitions and encoding profile. Preview and export required. No cloud upload.

Version 1.1 adds a user-requested batch workflow: import product folders, suggest Model/Hands roles, allow swaps, inspect/edit settings separately for every product, then export sequentially into separate product subfolders under a chosen destination. Ambiguous file counts need explicit pairing. Image role detection is a heuristic, not guaranteed recognition. Existing exports are preserved with numbered output names.

## Evidence
Reference: ==- МОНТАЖ (2).mp4, 1080x1080 H.264, 30 fps, 658 frames, 2,949,732 bytes. Premiere project and two MOV sources supplied.

## Stack
Implementation choice: Python processing, local HTML interface, bundled Windows runtime. Batch files for development launch and distributable build. Installer requested explicitly.
