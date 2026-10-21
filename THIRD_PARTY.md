# Third-party components

OUTMAX Cut uses local open-source components. The packaged program includes Python,
Flask (BSD-3-Clause), Werkzeug (BSD-3-Clause), Waitress (ZPL-2.1), NumPy (BSD-3-Clause),
OpenCV (Apache-2.0), pywebview (BSD-3-Clause), pythonnet (MIT), and their dependencies.
PyInstaller's bootloader exception permits distribution of the bundled program.
Dependency copyright notices are also included in installed package metadata where available.

Manrope by Mikhail Sharanda / Mirko Velimirovic is used under the SIL Open Font
License; the full license is in `assets/Manrope-OFL.txt`.

FFmpeg and ffprobe are redistributed as separate executable programs, invoked through
the command line. This build uses Gyan's FFmpeg 8.0.1 full build with libx264,
licensed under GPL version 3 or later. The actual configuration and copyright
notice are shipped in `_internal/licenses`. Source and build recipes:

- https://ffmpeg.org/download.html
- https://github.com/FFmpeg/FFmpeg/tree/n8.0.1
- https://www.gyan.dev/ffmpeg/builds/
- https://github.com/ffmpeg-builds
- https://www.videolan.org/developers/x264.html

Before broader redistribution, retain all third-party notices and supply the
corresponding source for the FFmpeg binaries in accordance with their licenses.
This project does not include or copy the Film Impact or Adobe implementation.
Its Lens Blur transition is an independent approximation. The supplied reference
video belongs to the user and is included solely as their chosen reference.

Microsoft Edge WebView2 Runtime is a Microsoft component used by the Windows
interface. It is installed on most Windows 10/11 PCs; it is not redistributed here.
