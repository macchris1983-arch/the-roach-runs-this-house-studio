#!/bin/bash
# One-time Colab setup for the free open-source animation pipeline.
set -e
apt-get -qq -y install espeak-ng > /dev/null
pip -q install -U "diffusers>=0.32" "transformers>=4.46" accelerate sentencepiece bitsandbytes "imageio[ffmpeg]" "kokoro>=0.9.4" soundfile
echo "SETUP OK"
