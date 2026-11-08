#!/bin/bash
# One-time Colab setup for the free open-source animation pipeline.
set -e
apt-get -qq -y install espeak-ng > /dev/null
pip -q install -U "diffusers>=0.32" "transformers>=4.46" accelerate sentencepiece bitsandbytes "imageio[ffmpeg]" kokoro-onnx soundfile
mkdir -p /content/models
cd /content/models
[ -f kokoro-v1.0.onnx ] || wget -q https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
[ -f voices-v1.0.bin ] || wget -q https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cd - > /dev/null
echo "SETUP OK"
