import subprocess

def ffmpeg_convert_to_mp4(ffmpeg_bin: str, input_webm: str, output_mp4: str):
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_webm,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_mp4
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def ensure_wav_16k_mono(ffmpeg_bin: str, input_path: str, output_wav: str):
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        output_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
