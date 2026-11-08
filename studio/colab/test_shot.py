"""Free open-source test shot for The Roach Runs This House (run on Google Colab, T4 GPU).

E00 shot s1: the Roach on the kitchen counter, talking to camera.
Tools (all free/open source):
  - SDXL-Turbo (stabilityai/sdxl-turbo) for one consistent 3D kitchen background
  - the owner's 3D character cut-outs (assets/characters/cutouts-3d) for identity
  - LTX-Video (Lightricks/LTX-Video) image-to-video for motion
  - Kokoro-82M (hexgrad/Kokoro-82M) for the voice
Run:  !python studio/colab/test_shot.py   (from the repo root, after setup.sh)
"""
import gc, os, subprocess, sys
import numpy as np
import torch
from PIL import Image

OUT = os.environ.get("OUT", "/content/out")
os.makedirs(OUT, exist_ok=True)
W, H = 480, 832          # 9:16, divisible by 32 (LTX requirement)
FPS = 24
NUM_FRAMES = 97          # ~4 s (LTX wants 8k+1 frames)
SEED = 1234
dev = "cuda"


def free():
    gc.collect()
    torch.cuda.empty_cache()


# ---------------------------------------------------------------- 1) background (made once, reused by every shot)
BG = f"{OUT}/kitchen_bg.png"
if not os.path.exists(BG):
    from diffusers import AutoPipelineForText2Image
    t2i = AutoPipelineForText2Image.from_pretrained("stabilityai/sdxl-turbo", torch_dtype=torch.float16, variant="fp16").to(dev)
    img = t2i(
        prompt=("3D animated feature film still, cozy family kitchen interior in Oakland, warm wood cabinets, "
                "tiled kitchen counter across the bottom of the frame, window on the left with warm afternoon sunlight, "
                "living room with a brown couch softly blurred in the background, soft shadows, no people, no text"),
        num_inference_steps=2, guidance_scale=0.0, width=512, height=896,
        generator=torch.Generator(dev).manual_seed(SEED)).images[0]
    img.resize((W, H), Image.LANCZOS).save(BG)
    del t2i; free()
bg = Image.open(BG).convert("RGB").resize((W, H), Image.LANCZOS)

# ---------------------------------------------------------------- 2) start frame: Roach cut-out on the counter
roach = Image.open("assets/characters/cutouts-3d/roach.png").convert("RGBA")
scale = (H * 0.55) / roach.height                 # Roach fills about half the frame height
roach = roach.resize((int(roach.width * scale), int(roach.height * scale)), Image.LANCZOS)
frame = bg.copy()
x = (W - roach.width) // 2
y = int(H * 0.88) - roach.height                   # feet on the counter line
frame.paste(roach, (x, y), roach)
START = f"{OUT}/e00_s1_start.png"
frame.save(START)

# ---------------------------------------------------------------- 3) motion with LTX-Video (text encoder in 8-bit first, then the video model)
PROMPT = ("A cartoon cockroach standing on a kitchen counter talks to the camera like a cocky talk-show host: "
          "he spreads both arms wide, then points one finger at the camera and grins, antennae bouncing, mouth moving as he talks. "
          "3D animated feature film style, warm afternoon light, static camera, the kitchen background stays still.")
NEG = "worst quality, blurry, distorted, extra legs, extra arms, deformed, text, watermark, camera shake, morphing"

from transformers import T5EncoderModel, T5Tokenizer, BitsAndBytesConfig
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video

te = T5EncoderModel.from_pretrained("Lightricks/LTX-Video", subfolder="text_encoder",
                                    quantization_config=BitsAndBytesConfig(load_in_8bit=True), device_map="auto")
tok = T5Tokenizer.from_pretrained("Lightricks/LTX-Video", subfolder="tokenizer")
enc = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", text_encoder=te, tokenizer=tok,
                                              transformer=None, vae=None, torch_dtype=torch.float16)
with torch.no_grad():
    pe, pm, ne, nm = enc.encode_prompt(prompt=PROMPT, negative_prompt=NEG, do_classifier_free_guidance=True,
                                       max_sequence_length=128, device=dev)
pe, pm, ne, nm = [t.to("cpu") for t in (pe, pm, ne, nm)]
del enc, te; free()

DTYPE = torch.float16 if os.environ.get("LTX_FP32") != "1" else torch.float32
pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", text_encoder=None, tokenizer=None, torch_dtype=DTYPE)
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling()
frames = pipe(image=frame, prompt_embeds=pe.to(dev, DTYPE), prompt_attention_mask=pm.to(dev),
              negative_prompt_embeds=ne.to(dev, DTYPE), negative_prompt_attention_mask=nm.to(dev),
              width=W, height=H, num_frames=NUM_FRAMES, num_inference_steps=30, guidance_scale=3.0,
              generator=torch.Generator("cpu").manual_seed(SEED)).frames[0]
arr = np.array(frames[len(frames) // 2]).astype(np.float32)
print("mid-frame mean brightness:", arr.mean(), "(near 0 = broken fp16 run; rerun with LTX_FP32=1)")
SILENT = f"{OUT}/e00_s1_silent.mp4"
export_to_video(frames, SILENT, fps=FPS)
del pipe; free()

# ---------------------------------------------------------------- 4) voice with Kokoro
from kokoro import KPipeline
import soundfile as sf
LINE = "Welcome to my house. Don't touch nothin', it's priced."
tts = KPipeline(lang_code="a")
audio = np.concatenate([a for _, _, a in tts(LINE, voice="am_puck", speed=1.1)])
WAV = f"{OUT}/e00_s1_roach.wav"
sf.write(WAV, audio, 24000)

# ---------------------------------------------------------------- 5) mux
FINAL = f"{OUT}/e00_s1_test.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", SILENT, "-i", WAV, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", FINAL], check=True)
print("DONE", FINAL)
