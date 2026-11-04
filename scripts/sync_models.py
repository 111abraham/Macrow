import os
import sys
import json
import subprocess
import struct
from pathlib import Path

def is_gguf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except Exception:
        return False

def get_ollama_models(ollama_dir: Path):
    models = []
    # Check manifests and manifests-v2
    for manifest_dir_name in ["manifests-v2", "manifests"]:
        md = ollama_dir / manifest_dir_name
        if not md.exists():
            continue
        for root, dirs, files in os.walk(md):
            for file in files:
                mpath = Path(root) / file
                try:
                    with open(mpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tag = file
                    # relative path gives namespace/model
                    rel = mpath.relative_to(md)
                    parts = rel.parts
                    # e.g. ("ollama.com", "library", "qwen2.5vl", "7b")
                    if len(parts) >= 2:
                        model_name = parts[-2]
                        tag = parts[-1]
                        full_tag = f"{model_name}:{tag}"
                    else:
                        full_tag = file
                    
                    layers = data.get("layers", [])
                    model_digest = None
                    mmproj_digest = None
                    for layer in layers:
                        mtype = layer.get("mediaType", "")
                        digest = layer.get("digest", "")
                        if "model" in mtype:
                            model_digest = digest.replace("sha256:", "sha256-")
                        elif "projector" in mtype:
                            mmproj_digest = digest.replace("sha256:", "sha256-")
                    if model_digest:
                        models.append({
                            "tag": full_tag,
                            "model_digest": model_digest,
                            "mmproj_digest": mmproj_digest,
                        })
                except Exception:
                    pass
    return models

def sync_ollama_to_lmstudio():
    user_profile = Path(os.environ.get("USERPROFILE", "C:\\Users\\PC"))
    ollama_dir = user_profile / ".ollama"
    blobs_dir = ollama_dir / "blobs"
    if not blobs_dir.exists():
        blobs_dir = ollama_dir / "models" / "blobs"
    
    lmstudio_dir = user_profile / ".lmstudio" / "models"
    lmstudio_dir.mkdir(parents=True, exist_ok=True)

    if not blobs_dir.exists():
        print(f"Ollama blobs directory not found at {blobs_dir}")
        return

    existing_ggufs = set()
    for root, dirs, files in os.walk(lmstudio_dir):
        for f in files:
            if f.endswith(".gguf"):
                fp = Path(root) / f
                try:
                    st = os.stat(fp)
                    existing_ggufs.add((st.st_ino, st.st_size))
                except Exception:
                    pass

    models = get_ollama_models(ollama_dir)
    print(f"Found {len(models)} Ollama model manifests.")

    for m in models:
        blob_path = blobs_dir / m["model_digest"]
        if not blob_path.exists():
            continue
        if not is_gguf(blob_path):
            continue

        try:
            st = os.stat(blob_path)
            if (st.st_ino, st.st_size) in existing_ggufs:
                # Already linked in LM Studio
                continue
        except Exception:
            pass

        tag_clean = m["tag"].replace(":", "-").replace("/", "-")
        target_dir = lmstudio_dir / "ollama" / tag_clean
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{tag_clean}.gguf"

        if target_file.exists():
            continue

        print(f"Linking Ollama model {m['tag']} to LM Studio ({target_file.name})...")
        try:
            # Create NTFS hardlink (zero disk copy)
            os.link(blob_path, target_file)
            print(f"  -> Linked successfully: {target_file}")
            existing_ggufs.add((st.st_ino, st.st_size))
        except Exception as e:
            print(f"  -> Failed to hardlink {m['tag']}: {e}")

def sync_lmstudio_to_ollama():
    user_profile = Path(os.environ.get("USERPROFILE", "C:\\Users\\PC"))
    lmstudio_dir = user_profile / ".lmstudio" / "models"
    ollama_exe = Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\PC\\AppData\\Local")) / "Programs" / "Ollama" / "ollama.exe"
    if not ollama_exe.exists():
        ollama_exe = "ollama"

    if not lmstudio_dir.exists():
        return

    # Check registered Ollama models
    try:
        res = subprocess.run([str(ollama_exe), "list"], capture_output=True, text=True, check=True)
        registered = set()
        for line in res.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                registered.add(parts[0].lower())
    except Exception as e:
        print(f"Error querying Ollama: {e}")
        return

    for root, dirs, files in os.walk(lmstudio_dir):
        for f in files:
            if f.endswith(".gguf") and not f.startswith("mmproj"):
                full_path = Path(root) / f
                # Clean tag name
                base_name = full_path.stem.lower()
                clean_tag = base_name.replace(" ", "-").replace("_", "-")
                if "gemma-4-e4b" in clean_tag:
                    tag = "gemma4:e4b"
                elif "gemma-4-12b" in clean_tag:
                    tag = "gemma4:12b"
                elif "gemma-4-26b" in clean_tag:
                    tag = "gemma4:26b"
                elif "qwen3.8-27b" in clean_tag and "smaller" in clean_tag:
                    tag = "qwen3.8:27b-smaller"
                elif "qwen3.8-27b" in clean_tag:
                    tag = "qwen3.8:27b"
                elif "qwen2.5-vl-7b" in clean_tag or "qwen2.5vl" in clean_tag:
                    tag = "qwen2.5vl:7b"
                else:
                    tag = f"lmstudio-{clean_tag[:40]}"

                if tag in registered or f"{tag}:latest" in registered:
                    continue

                print(f"Registering LM Studio model {f} as Ollama model {tag}...")
                modelfile_content = f'FROM "{full_path}"\n'
                # Check for mmproj in same dir
                mmproj = list(Path(root).glob("mmproj*.gguf"))
                if mmproj:
                    modelfile_content += f'ADAPTER "{mmproj[0]}"\n'

                temp_modelfile = user_profile / f"Modelfile_temp_{tag.replace(':', '_')}"
                try:
                    with open(temp_modelfile, "w", encoding="utf-8") as mf:
                        mf.write(modelfile_content)
                    c_res = subprocess.run(
                        [str(ollama_exe), "create", tag, "-f", str(temp_modelfile)],
                        capture_output=True,
                        text=True
                    )
                    if c_res.returncode == 0:
                        print(f"  -> Successfully created Ollama model {tag}")
                        registered.add(tag)
                    else:
                        print(f"  -> Ollama create failed: {c_res.stderr}")
                finally:
                    if temp_modelfile.exists():
                        temp_modelfile.unlink()

def main():
    print("=" * 60)
    print("  Bidirectional Zero-Copy Model Sync: Ollama <-> LM Studio / Bionic")
    print("=" * 60)
    print("\n1. Syncing Ollama -> LM Studio / Bionic...")
    sync_ollama_to_lmstudio()
    print("\n2. Syncing LM Studio / Bionic -> Ollama...")
    sync_lmstudio_to_ollama()
    print("\n[OK] Model synchronization complete.")

if __name__ == "__main__":
    main()
