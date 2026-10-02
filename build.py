"""Build script for packaging CS2 Voice Translator as a standalone .exe"""

import PyInstaller.__main__
import shutil
import os

DIST_DIR = os.path.join(os.path.dirname(__file__), "dist")
BUILD_DIR = os.path.join(os.path.dirname(__file__), "build")

# Clean previous builds
for d in [DIST_DIR, BUILD_DIR]:
    if os.path.exists(d):
        shutil.rmtree(d)

PyInstaller.__main__.run([
    "app.py",
    "--name=CS2Translator",
    "--onedir",
    "--windowed",
    "--noconfirm",
    "--clean",
    # Hidden imports that PyInstaller may miss
    "--hidden-import=pyaudiowpatch",
    "--hidden-import=keyring.backends.Windows",
    "--hidden-import=numpy",
    # openai imports pandas lazily for optional helpers the app never calls.
    # PyInstaller follows it anyway, and with the eval tools installed it
    # continues through scipy into torch and tensorflow (a 5.5 GB build).
    "--exclude-module=pandas",
    "--exclude-module=torch",
    "--exclude-module=tensorflow",
])

print("\nBuild complete! Output in dist/CS2Translator/")
