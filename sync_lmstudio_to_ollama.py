"""
Syncs LM Studio GGUF models into Ollama Desktop using NTFS Hardlinks (0 extra disk space).
Usage:
    python sync_lmstudio_to_ollama.py
"""

import os
import sys
import subprocess
from pathlib import Path

LMSTUDIO_MODELS = Path(r"C:\Users\PC\.lmstudio\models")
OLLAMA_EXE = Path(r"C:\Users\PC\AppData\Local\Programs\Ollama\ollama.exe")
OLLAMA_BLOBS = Path(r"C:\Users\PC\.ollama\models\blobs")


def main():
    if not LMSTUDIO_MODELS.exists():
        print(f"LM Studio models directory not found at: {LMSTUDIO_MODELS}")
        return

    if not OLLAMA_EXE.exists():
        print(f"Ollama executable not found at: {OLLAMA_EXE}")
        return

    print("Scanning LM Studio models...")
    gguf_files = list(LMSTUDIO_MODELS.rglob("*.gguf"))
    # Exclude mmproj multimodal projector files from standalone model creation
    base_ggufs = [f for f in gguf_files if not f.name.startswith("mmproj-")]

    if not base_ggufs:
        print("No base .gguf models found in LM Studio directory.")
        return

    print(f"Found {len(base_ggufs)} model files.")
    for gguf in base_ggufs:
        # Create friendly name
        rel = gguf.relative_to(LMSTUDIO_MODELS)
        clean_name = gguf.stem.lower()
        for char in ("_", " ", ".", "-it", "-gguf"):
            clean_name = clean_name.replace(char, "-")
        while "--" in clean_name:
            clean_name = clean_name.replace("--", "-")
        clean_name = clean_name.strip("-")

        print(f"\nProcessing: {gguf.name} -> {clean_name}")

        modelfile_content = f'FROM "{gguf.as_posix()}"\n'
        tmp_modelfile = Path("temp_modelfile")
        tmp_modelfile.write_text(modelfile_content, encoding="utf-8")

        try:
            # Check if model already exists in Ollama
            res = subprocess.run([str(OLLAMA_EXE), "list"], capture_output=True, text=True)
            if clean_name in res.stdout:
                print(f"  Already registered in Ollama as '{clean_name}'. Skipping.")
                continue

            print(f"  Creating model in Ollama...")
            create_res = subprocess.run(
                [str(OLLAMA_EXE), "create", clean_name, "-f", str(tmp_modelfile)],
                capture_output=True,
                text=True,
            )
            if create_res.returncode == 0:
                print(f"  Successfully registered '{clean_name}' in Ollama!")
            else:
                print(f"  Error creating model: {create_res.stderr}")
        finally:
            if tmp_modelfile.exists():
                tmp_modelfile.unlink()


if __name__ == "__main__":
    main()
