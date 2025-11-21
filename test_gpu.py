import torch

print("=" * 60)
print("CS2 Translator - GPU Detection Test")
print("=" * 60)
print()

if torch.cuda.is_available():
    device = "cuda"
    gpu_name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f"[SUCCESS] GPU detected: {gpu_name}")
    print(f"          VRAM: {vram:.1f} GB")
    print(f"          CUDA Version: {torch.version.cuda}")
    print()
    print("[SUCCESS] GPU will be used for Whisper model!")
else:
    device = "cpu"
    print("[WARNING] No GPU detected, will use CPU")

print()
print(f"Device that will be used: {device}")
